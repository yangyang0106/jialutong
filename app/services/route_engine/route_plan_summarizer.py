from typing import Any

from app.services.route_engine.baidu_route_parser import normalize_baidu_route
from app.services.route_engine.decision_point_extractor import extract_decision_points


def summarize_route_plan(response: dict[str, Any], input_data: dict[str, Any], route_index: int) -> dict[str, Any]:
    normalized = normalize_baidu_route(response, route_index)
    steps = extract_decision_points(
        normalized,
        {
            "routeId": f"advice-plan-{route_index}",
            "destinationName": input_data.get("destination", {}).get("name", ""),
            "origin": input_data.get("origin", {}),
            "destination": input_data.get("destination", {}),
        },
    )
    descriptions = []
    for segment in normalized.get("segments", []):
        text = segment.get("instruction") or segment.get("action") or ""
        if text and text not in descriptions:
            descriptions.append(text)
    transit_segments = [
        segment for segment in normalized.get("segments", []) if segment.get("mode") == "TRANSIT"
    ]
    walk_distance = sum(
        int(segment.get("distance") or 0)
        for segment in normalized.get("segments", [])
        if segment.get("mode") == "WALKING"
    )
    return {
        "index": route_index,
        "distance": int(normalized.get("distance") or 0),
        "duration": int(normalized.get("duration") or 0),
        "description": "；".join(descriptions[:8])[:800],
        "walkDistance": walk_distance,
        "transferCount": max(0, len(transit_segments) - 1),
        "riskPointCount": len([step for step in steps if step.get("riskLevel") != "LOW"]),
        "decisionPointCount": len(steps),
    }


def summarize_route_plans(response: dict[str, Any], input_data: dict[str, Any]) -> list[dict[str, Any]]:
    routes = ((response.get("result") or {}).get("routes") or [])[:5]
    return [summarize_route_plan(response, input_data, index) for index, _route in enumerate(routes)]
