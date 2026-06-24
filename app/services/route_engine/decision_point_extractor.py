import math
import re
from typing import Any

from app.services.route_engine.geo import calculate_distance, normalize_location
from app.services.route_engine.voice_generator import generate_step_voice


MERGE_DISTANCE_METERS = 20
MIN_WALK_CONNECTOR_METERS = 30
MAX_WALK_WITHOUT_CONFIRMATION_METERS = 380


def type_from_action(action: str) -> str | None:
    if re.search(r"左转|左前方|偏左|靠左|左后转|左转掉头", action or ""):
        return "LEFT"
    if re.search(r"右转|右前方|偏右|靠右|右后转", action or ""):
        return "RIGHT"
    if re.search(r"进入.*辅路|驶入.*辅路|转入.*辅路", action or ""):
        return "STRAIGHT"
    return None


def road_name_from_segment(segment: dict[str, Any]) -> str:
    if segment.get("roadName"):
        return segment["roadName"]
    match = re.search(r"(?:进入|转入)([^，,。]+?)(?:走|直行|$)", segment.get("instruction") or "")
    return match.group(1).strip() if match else ""


def risk_from_segment(segment: dict[str, Any], step_type: str) -> str:
    instruction = f"{segment.get('instruction') or ''}{segment.get('action') or ''}"
    if segment.get("facilityType") in {1, 2, 3}:
        return "HIGH"
    if re.search(r"过马路|穿过马路|横穿|人行横道|红绿灯|地下通道|天桥", instruction):
        return "HIGH"
    if step_type in {"SUBWAY_IN", "SUBWAY_OUT", "TRANSFER"}:
        return "HIGH"
    if step_type in {"BUS_ON", "BUS_OFF"}:
        return "MEDIUM"
    return "LOW"


def requires_review(step_type: str, risk_level: str) -> bool:
    return risk_level == "HIGH" or step_type in {
        "START",
        "DESTINATION",
        "BUS_ON",
        "BUS_OFF",
        "SUBWAY_IN",
        "SUBWAY_OUT",
        "TRANSFER",
    }


def create_candidate(
    step_type: str,
    segment: dict[str, Any],
    location: Any,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    risk_level = risk_from_segment(segment, step_type)
    return {
        "type": step_type,
        "location": normalize_location(location),
        "riskLevel": risk_level,
        "requiresFamilyReview": requires_review(step_type, risk_level),
        "roadName": road_name_from_segment(segment),
        "source": {
            "provider": segment.get("provider") or "BAIDU_MAP",
            "sourceSectionIndex": segment.get("sourceSectionIndex"),
            "sourceStepIndexes": [segment.get("sourceStepIndex")],
            "instruction": segment.get("instruction") or "",
            "polylineIndex": segment.get("sourcePolylineIndex"),
            "polyline": segment.get("polyline") or [],
        },
        **(extra or {}),
    }


def polyline_points(polyline: list[float]) -> list[dict[str, float]]:
    return [
        {"latitude": float(polyline[index]), "longitude": float(polyline[index + 1])}
        for index in range(0, max(len(polyline) - 1, 0), 2)
    ]


def interpolate_point(start: dict[str, float], end: dict[str, float], ratio: float) -> dict[str, float]:
    return {
        "latitude": start["latitude"] + (end["latitude"] - start["latitude"]) * ratio,
        "longitude": start["longitude"] + (end["longitude"] - start["longitude"]) * ratio,
    }


def reassurance_locations(segment: dict[str, Any]) -> list[dict[str, float]]:
    if segment.get("mode") != "WALKING" or float(segment.get("distance") or 0) <= MAX_WALK_WITHOUT_CONFIRMATION_METERS:
        return []
    points = polyline_points(segment.get("polyline") or [])
    if len(points) < 2:
        return []
    targets = []
    target = MAX_WALK_WITHOUT_CONFIRMATION_METERS
    while target < float(segment.get("distance") or 0) - 100:
        targets.append(target)
        target += MAX_WALK_WITHOUT_CONFIRMATION_METERS
    locations = []
    walked = 0
    target_index = 0
    for index in range(1, len(points)):
        segment_length = calculate_distance(
            points[index - 1]["latitude"],
            points[index - 1]["longitude"],
            points[index]["latitude"],
            points[index]["longitude"],
        )
        while target_index < len(targets) and walked + segment_length >= targets[target_index]:
            if segment_length:
                locations.append(
                    interpolate_point(
                        points[index - 1],
                        points[index],
                        (targets[target_index] - walked) / segment_length,
                    )
                )
            target_index += 1
        walked += segment_length
    return locations


def landmark_hint_from_segment(segment: dict[str, Any]) -> str:
    instruction = segment.get("instruction") or ""
    road = road_name_from_segment(segment)
    if "辅路" in instruction and road:
        return f"{road}路口"
    return ""


def approach_polyline(previous: dict[str, Any] | None, candidate: dict[str, Any], segments: list[dict[str, Any]]) -> list[float]:
    end_index = candidate.get("source", {}).get("sourceSectionIndex")
    previous_index = previous.get("source", {}).get("sourceSectionIndex") if previous else end_index
    if not isinstance(end_index, int):
        return candidate.get("source", {}).get("polyline") or []
    start_index = min(previous_index, end_index) if isinstance(previous_index, int) else end_index
    result: list[float] = []
    for segment in segments[start_index : end_index + 1]:
        result.extend(segment.get("polyline") or [])
    return result


def build_transit_candidate(segment: dict[str, Any], step_type: str, station: dict[str, Any] | None) -> dict[str, Any]:
    transit = segment.get("transit") or {}
    return create_candidate(
        step_type,
        segment,
        station.get("location") if station else None,
        {
            "transit": {
                "vehicle": transit.get("vehicle"),
                "lineName": transit.get("lineName"),
                "direction": transit.get("direction"),
                "stationName": station.get("title") if station else "",
                "accessName": station.get("accessName") if station else "",
                "stationCount": transit.get("stationCount"),
            }
        },
    )


def is_station_transfer_walk(segment: dict[str, Any] | None) -> bool:
    return bool(
        segment
        and segment.get("mode") == "WALKING"
        and re.search(r"站内|换乘|通道", f"{segment.get('instruction') or ''}{segment.get('action') or ''}")
    )


def find_connected_subway(segments: list[dict[str, Any]], start_index: int, direction: int) -> dict[str, Any] | None:
    index = start_index + direction
    while 0 <= index < len(segments):
        segment = segments[index]
        if segment.get("mode") == "TRANSIT":
            return segment if (segment.get("transit") or {}).get("vehicle") == "SUBWAY" else None
        if not is_station_transfer_walk(segment):
            return None
        index += direction
    return None


def get_next_transit(segments: list[dict[str, Any]], start_index: int) -> dict[str, Any] | None:
    for index in range(start_index + 1, len(segments)):
        segment = segments[index]
        if segment.get("mode") == "TRANSIT":
            return segment
        if not is_station_transfer_walk(segment) and segment.get("mode") != "WALKING":
            return None
    return None


def is_walking_run_end(segments: list[dict[str, Any]], index: int) -> bool:
    next_segment = segments[index + 1] if index + 1 < len(segments) else None
    return not next_segment or next_segment.get("mode") != "WALKING" or is_station_transfer_walk(next_segment)


def walking_connector_copy(segments: list[dict[str, Any]], segment_index: int, destination_name: str) -> dict[str, str]:
    next_transit = get_next_transit(segments, segment_index)
    if next_transit and next_transit.get("transit"):
        transit = next_transit["transit"]
        station_name = transit.get("getOn", {}).get("title") or (
            "地铁站入口" if transit.get("vehicle") == "SUBWAY" else "公交站"
        )
        return {"title": f"步行到{station_name}", "shortAction": f"走到{station_name}"}
    return {"title": f"步行到{destination_name}", "shortAction": "继续走到目的地"}


def merge_nearby_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for candidate in candidates:
        previous = result[-1] if result else None
        if (
            previous
            and previous.get("type") == candidate.get("type")
            and previous.get("location")
            and candidate.get("location")
            and calculate_distance(
                previous["location"]["latitude"],
                previous["location"]["longitude"],
                candidate["location"]["latitude"],
                candidate["location"]["longitude"],
            )
            <= MERGE_DISTANCE_METERS
        ):
            previous["source"]["sourceStepIndexes"].extend(candidate["source"]["sourceStepIndexes"])
            previous["riskLevel"] = "HIGH" if candidate.get("riskLevel") == "HIGH" else previous.get("riskLevel")
            previous["requiresFamilyReview"] = previous.get("requiresFamilyReview") or candidate.get("requiresFamilyReview")
            continue
        result.append(candidate)
    return result


def walking_candidate_gap_distance(previous: dict[str, Any], candidate: dict[str, Any], segments: list[dict[str, Any]]) -> float:
    start_index = previous.get("source", {}).get("sourceSectionIndex")
    end_index = candidate.get("source", {}).get("sourceSectionIndex")
    if not isinstance(start_index, int) or not isinstance(end_index, int):
        return 0
    gap_segments = segments[min(start_index, end_index) : max(start_index, end_index) + 1]
    if not all(segment.get("mode") == "WALKING" and not is_station_transfer_walk(segment) for segment in gap_segments):
        return 0
    return sum(float(segment.get("distance") or 0) for segment in gap_segments)


def fill_long_walking_gaps(candidates: list[dict[str, Any]], segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for candidate in candidates:
        previous = result[-1] if result else None
        walking_distance = (
            walking_candidate_gap_distance(previous, candidate, segments)
            if previous and previous.get("location") and candidate.get("location")
            else 0
        )
        if not walking_distance or walking_distance <= MAX_WALK_WITHOUT_CONFIRMATION_METERS:
            result.append(candidate)
            continue
        distance = calculate_distance(
            previous["location"]["latitude"],
            previous["location"]["longitude"],
            candidate["location"]["latitude"],
            candidate["location"]["longitude"],
        )
        if distance > walking_distance * 1.5 + 50:
            result.append(candidate)
            continue
        insert_count = math.ceil(distance / MAX_WALK_WITHOUT_CONFIRMATION_METERS) - 1
        for index in range(1, insert_count + 1):
            location = interpolate_point(previous["location"], candidate["location"], index / (insert_count + 1))
            result.append(
                create_candidate(
                    "STRAIGHT",
                    segments[candidate["source"]["sourceSectionIndex"]],
                    location,
                    {
                        "reassurance": True,
                        "riskLevel": "LOW",
                        "requiresFamilyReview": False,
                        "walkingTitle": "继续往前走",
                        "walkingShortAction": "继续往前走",
                        "fixedApproachPolyline": [
                            previous["location"]["latitude"],
                            previous["location"]["longitude"],
                            location["latitude"],
                            location["longitude"],
                        ],
                    },
                )
            )
        result.append(candidate)
    return result


def candidate_title(candidate: dict[str, Any], destination_name: str) -> str:
    transit = candidate.get("transit") or {}
    station_name = transit.get("stationName") or "当前站"
    station_inside_name = f"{station_name}内" if station_name.endswith("站") else f"{station_name}站内"
    access_name = transit.get("accessName") or ""
    direction = f"，开往{transit['direction']}" if transit.get("direction") else ""
    step_type = candidate.get("type")
    if step_type == "START":
        return "从起点出发"
    if step_type == "LEFT":
        return f"左转进入{candidate['roadName']}" if candidate.get("roadName") else "在前面路口左转"
    if step_type == "RIGHT":
        return f"右转进入{candidate['roadName']}" if candidate.get("roadName") else "在前面路口右转"
    if step_type == "STRAIGHT":
        return candidate.get("walkingTitle") or "继续往前走"
    if step_type == "BUS_ON":
        return f"在{transit.get('stationName') or '公交站'}乘坐{transit.get('lineName') or '公交车'}{direction}"
    if step_type == "BUS_OFF":
        return f"在{transit.get('stationName') or '目标站'}下车"
    if step_type == "SUBWAY_IN":
        return f"从{transit.get('stationName') or '地铁站'}{access_name or '家属确认的入口'}进站"
    if step_type == "SUBWAY_OUT":
        return f"从{transit.get('stationName') or '目标站'}{access_name or '家属确认的出口'}出站"
    if step_type == "TRANSFER":
        return f"在{station_inside_name}换乘{transit.get('lineName') or '下一条线路'}{direction}"
    if step_type == "DESTINATION":
        return f"到达{destination_name}"
    return "继续前进"


def candidate_short_action(candidate: dict[str, Any]) -> str:
    transit = candidate.get("transit") or {}
    crosses_road = re.search(r"过马路|穿过马路|横穿|人行横道|红绿灯", candidate.get("source", {}).get("instruction") or "")
    step_type = candidate.get("type")
    if step_type == "START":
        return "准备出发"
    if step_type == "LEFT":
        return "过马路左转" if crosses_road else "前面左转"
    if step_type == "RIGHT":
        return "过马路右转" if crosses_road else "前面右转"
    if step_type == "STRAIGHT":
        return candidate.get("walkingShortAction") or "继续往前走"
    if step_type == "BUS_ON":
        return f"等{transit.get('lineName') or '公交车'}"
    if step_type == "BUS_OFF":
        return "准备下车"
    if step_type == "SUBWAY_IN":
        return "进入地铁站"
    if step_type == "SUBWAY_OUT":
        return "走出地铁站"
    if step_type == "TRANSFER":
        return "站内换乘"
    if step_type == "DESTINATION":
        return "已经到达"
    return "继续前进"


def create_route_step(input_data: dict[str, Any]) -> dict[str, Any]:
    location = input_data.get("location") or {}
    return {
        "id": input_data.get("id") or "",
        "routeId": input_data.get("routeId") or "",
        "stepNo": int(input_data.get("stepNo") or 0),
        "type": input_data["type"],
        "title": input_data.get("title") or "",
        "shortAction": input_data.get("shortAction") or "",
        "location": {
            "latitude": None if location.get("latitude") is None else float(location.get("latitude")),
            "longitude": None if location.get("longitude") is None else float(location.get("longitude")),
        },
        "arriveRadius": int(input_data.get("arriveRadius") or 30),
        "showDirectionDistance": int(input_data.get("showDirectionDistance") or 30),
        "direction": input_data.get("direction") or "",
        "roadName": input_data.get("roadName") or "",
        "landmarkHint": input_data.get("landmarkHint") or "",
        "riskLevel": input_data.get("riskLevel") or "LOW",
        "imageUrl": input_data.get("imageUrl") or "",
        "imageStatus": input_data.get("imageStatus") or "NONE",
        "voice": input_data.get("voice") or {},
        "transit": input_data.get("transit"),
        "requiresFamilyReview": bool(input_data.get("requiresFamilyReview")),
        "reviewStatus": input_data.get("reviewStatus") or "PENDING",
        "reviewNote": input_data.get("reviewNote") or "",
        "stepResult": input_data.get("stepResult"),
        "source": input_data.get("source"),
    }


def extract_decision_points(normalized_route: dict[str, Any], route_context: dict[str, Any]) -> list[dict[str, Any]]:
    segments = normalized_route.get("segments") or []
    if not segments:
        raise ValueError("路线中没有可解析的路段")
    candidates = [
        create_candidate("START", segments[0], route_context.get("origin") or segments[0].get("startLocation"))
    ]
    for segment_index, segment in enumerate(segments):
        if segment.get("mode") == "WALKING":
            if is_station_transfer_walk(segment):
                continue
            for location in reassurance_locations(segment):
                candidates.append(
                    create_candidate(
                        "STRAIGHT",
                        segment,
                        location,
                        {
                            "reassurance": True,
                            "riskLevel": "LOW",
                            "requiresFamilyReview": False,
                            "walkingTitle": f"继续沿{segment['roadName']}往前走" if segment.get("roadName") else "继续往前走",
                            "walkingShortAction": "继续往前走",
                        },
                    )
                )
            step_type = type_from_action(f"{segment.get('action') or ''}{segment.get('instruction') or ''}")
            if step_type:
                candidates.append(
                    create_candidate(
                        step_type,
                        segment,
                        segment.get("endLocation"),
                        {"landmarkHint": landmark_hint_from_segment(segment)},
                    )
                )
            if is_walking_run_end(segments, segment_index) and (
                float(segment.get("distance") or 0) >= MIN_WALK_CONNECTOR_METERS or not step_type
            ):
                copy = walking_connector_copy(segments, segment_index, route_context["destinationName"])
                candidates.append(
                    create_candidate(
                        "STRAIGHT",
                        segment,
                        segment.get("endLocation"),
                        {"walkingTitle": copy["title"], "walkingShortAction": copy["shortAction"]},
                    )
                )
            continue

        transit = segment.get("transit") or {}
        if transit.get("vehicle") == "BUS":
            candidates.append(build_transit_candidate(segment, "BUS_ON", transit.get("getOn")))
            candidates.append(build_transit_candidate(segment, "BUS_OFF", transit.get("getOff")))
        elif transit.get("vehicle") == "SUBWAY":
            previous_subway = find_connected_subway(segments, segment_index, -1)
            next_subway = find_connected_subway(segments, segment_index, 1)
            candidates.append(
                build_transit_candidate(
                    segment,
                    "TRANSFER" if previous_subway else "SUBWAY_IN",
                    transit.get("getOn"),
                )
            )
            if not next_subway:
                candidates.append(build_transit_candidate(segment, "SUBWAY_OUT", transit.get("getOff")))

    candidates.append(
        create_candidate(
            "DESTINATION",
            segments[-1],
            segments[-1].get("endLocation") or route_context.get("destination"),
        )
    )

    merged = fill_long_walking_gaps(merge_nearby_candidates(candidates), segments)
    steps = []
    for index, candidate in enumerate(merged):
        previous = merged[index - 1] if index else None
        candidate["source"]["polyline"] = candidate.get("fixedApproachPolyline") or approach_polyline(previous, candidate, segments)
        previous_distance = (
            calculate_distance(
                previous["location"]["latitude"],
                previous["location"]["longitude"],
                candidate["location"]["latitude"],
                candidate["location"]["longitude"],
            )
            if previous and previous.get("location") and candidate.get("location")
            else None
        )
        arrive_radius = max(10, math.floor(previous_distance / 3)) if previous_distance is not None and previous_distance <= 45 else 30
        base_step = create_route_step(
            {
                "id": f"{route_context['routeId']}-step-{index + 1}",
                "routeId": route_context["routeId"],
                "stepNo": index + 1,
                "type": candidate["type"],
                "title": candidate_title(candidate, route_context["destinationName"]),
                "shortAction": candidate_short_action(candidate),
                "location": candidate.get("location"),
                "roadName": candidate.get("roadName"),
                "landmarkHint": candidate.get("landmarkHint") or "",
                "arriveRadius": arrive_radius,
                "riskLevel": candidate.get("riskLevel"),
                "imageStatus": "NONE",
                "transit": candidate.get("transit"),
                "requiresFamilyReview": candidate.get("requiresFamilyReview"),
                "reviewStatus": "PENDING",
                "source": candidate.get("source"),
            }
        )
        base_step["voice"] = generate_step_voice(base_step, route_context["destinationName"])
        steps.append(base_step)
    return steps
