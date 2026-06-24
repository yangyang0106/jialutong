import re
from typing import Any

from app.services.route_engine.geo import normalize_location


def strip_html(value: Any) -> str:
    return re.sub(r"<[^>]+>", "", str(value or ""))


def first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value
    return ""


def parse_path(path: Any) -> list[float]:
    if not isinstance(path, str) or not path:
        return []
    points: list[float] = []
    for value in path.split(";"):
        try:
            longitude, latitude = [float(item) for item in value.split(",", 1)]
        except (ValueError, TypeError):
            continue
        points.extend([latitude, longitude])
    return points


def extract_access_name(value: Any) -> str:
    text = strip_html(value)
    match = re.search(
        r"(?:地铁站)?([A-Za-z]?\d+\s*(?:号)?(?:出入)?口|[A-Za-z]\s*(?:出入)?口)",
        text,
        flags=re.I,
    )
    return re.sub(r"\s+", "", match.group(1)) if match else ""


def clean_station_name(value: Any) -> str:
    return re.sub(
        r"[（(]\s*[A-Za-z]?\d+\s*(?:号)?(?:出入)?口\s*[）)]",
        "",
        str(value or ""),
        flags=re.I,
    ).strip()


def station_access(station: dict[str, Any], detail: dict[str, Any], kind: str) -> str:
    prefix = "entrance" if kind == "entrance" else "exit"
    direct = first_text(
        station.get("accessName"),
        station.get(f"{prefix}_name"),
        station.get(prefix),
        detail.get(f"{prefix}_name"),
        detail.get(prefix),
    )
    if direct:
        return direct
    return extract_access_name(
        first_text(
            station.get("name"),
            station.get("start_name"),
            station.get("end_name"),
            station.get("instructions"),
            station.get("instruction"),
            detail.get("instructions"),
            detail.get("instruction"),
        )
    )


def _walking_segment(step: dict[str, Any], section_index: int, step_index: int) -> dict[str, Any]:
    instruction = strip_html(step.get("instruction"))
    return {
        "provider": "BAIDU_MAP",
        "mode": "WALKING",
        "vehicle": None,
        "action": f"{step.get('turn_type') or ''} {instruction}".strip(),
        "instruction": instruction,
        "roadName": step.get("road_name") or "",
        "direction": step.get("direction") or "",
        "distance": int(float(step.get("distance") or 0)),
        "facilityType": int(float(step.get("traffic_condition") or 0)),
        "startLocation": normalize_location(step.get("start_location")),
        "endLocation": normalize_location(step.get("end_location")),
        "polyline": parse_path(step.get("path")),
        "sourceSectionIndex": section_index,
        "sourceStepIndex": step_index,
        "sourcePolylineIndex": None,
    }


def _vehicle_detail(step: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    vehicle_info = step.get("vehicle_info") or {}
    detail = vehicle_info.get("detail") or step.get("vehicle") or {}
    return vehicle_info, detail


def _transit_vehicle(step: dict[str, Any]) -> str:
    vehicle_info, detail = _vehicle_detail(step)
    raw_type = str(vehicle_info.get("type", detail.get("type", ""))).upper()
    name = detail.get("name") or step.get("instructions") or step.get("instruction") or ""
    if re.search(r"SUBWAY|地铁|轨道", f"{raw_type}{name}"):
        return "SUBWAY"
    try:
        if int(detail.get("type")) == 1:
            return "SUBWAY"
    except (TypeError, ValueError):
        pass
    return "BUS"


def _transit_segment(step: dict[str, Any], section_index: int, step_index: int) -> dict[str, Any]:
    _vehicle_info, detail = _vehicle_detail(step)
    vehicle = _transit_vehicle(step)
    get_on = detail.get("departure_station") or detail.get("start_info") or {}
    get_off = detail.get("arrive_station") or detail.get("end_info") or {}
    direction = first_text(detail.get("direction"), detail.get("direct_text"), step.get("direction"))
    return {
        "provider": "BAIDU_MAP",
        "mode": "TRANSIT",
        "vehicle": vehicle,
        "action": "",
        "instruction": strip_html(step.get("instructions") or step.get("instruction")),
        "roadName": "",
        "direction": direction,
        "distance": int(float(step.get("distance") or 0)),
        "facilityType": 0,
        "startLocation": normalize_location(get_on.get("location") or step.get("start_location")),
        "endLocation": normalize_location(get_off.get("location") or step.get("end_location")),
        "polyline": parse_path(step.get("path")),
        "sourceSectionIndex": section_index,
        "sourceStepIndex": step_index,
        "sourcePolylineIndex": None,
        "transit": {
            "vehicle": vehicle,
            "lineId": detail.get("uid") or detail.get("line_id") or "",
            "lineName": detail.get("name") or "",
            "direction": direction,
            "getOn": {
                "title": clean_station_name(
                    get_on.get("name") or get_on.get("start_name") or detail.get("start_name") or ""
                ),
                "location": get_on.get("location") or get_on.get("start_location") or step.get("start_location"),
                "accessName": station_access(get_on, detail, "entrance"),
            },
            "getOff": {
                "title": clean_station_name(
                    get_off.get("name") or get_off.get("end_name") or detail.get("end_name") or ""
                ),
                "location": get_off.get("location") or get_off.get("end_location") or step.get("end_location"),
                "accessName": station_access(get_off, detail, "exit"),
            },
            "stationCount": int(float(detail.get("stop_num") or 0)),
            "stations": detail.get("stop_info") or [],
        },
    }


def _is_transit_step(step: dict[str, Any]) -> bool:
    _vehicle_info, detail = _vehicle_detail(step)
    return (
        int(float(step.get("type") or 0)) == 3
        or bool(detail.get("name") or detail.get("line_id") or detail.get("start_name") or detail.get("end_name"))
    )


def _flatten_steps(source_steps: list[Any]) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    for step in source_steps or []:
        if isinstance(step, list):
            flattened.extend(item for item in step if isinstance(item, dict))
        elif isinstance(step, dict):
            flattened.append(step)
    return flattened


def normalize_baidu_route(response: dict[str, Any], route_index: int = 0) -> dict[str, Any]:
    routes = ((response or {}).get("result") or {}).get("routes") or []
    source_route = routes[route_index] if route_index < len(routes) else None
    if not source_route:
        raise ValueError("百度地图未返回可用路线")
    source_steps = _flatten_steps(source_route.get("steps") or [])
    segments = [
        _transit_segment(step, index, index)
        if _is_transit_step(step)
        else _walking_segment(step, index, index)
        for index, step in enumerate(source_steps)
    ]
    for index, segment in enumerate(segments):
        transit = segment.get("transit") or {}
        if transit.get("vehicle") != "SUBWAY":
            continue
        previous = segments[index - 1] if index > 0 else None
        next_segment = segments[index + 1] if index + 1 < len(segments) else None
        if not transit["getOn"].get("accessName") and previous and previous.get("mode") == "WALKING":
            transit["getOn"]["accessName"] = extract_access_name(previous.get("instruction"))
        if not transit["getOff"].get("accessName") and next_segment and next_segment.get("mode") == "WALKING":
            transit["getOff"]["accessName"] = extract_access_name(next_segment.get("instruction"))
    travel_modes: list[str] = []
    for segment in segments:
        mode = segment.get("vehicle") or segment.get("mode")
        if mode not in travel_modes:
            travel_modes.append(mode)
    return {
        "distance": int(float(source_route.get("distance") or 0)),
        "duration": int(float(source_route.get("duration") or 0)),
        "bounds": source_route.get("bounds"),
        "polyline": [point for segment in segments for point in (segment.get("polyline") or [])],
        "travelModes": travel_modes,
        "segments": segments,
        "sourceRoute": source_route,
    }
