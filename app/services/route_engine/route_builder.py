from datetime import UTC, datetime
from typing import Any

from app.services.route_engine.baidu_route_parser import normalize_baidu_route
from app.services.route_engine.decision_point_extractor import extract_decision_points
from app.services.route_review import refresh_route_review


def build_family_route_from_baidu(
    response: dict[str, Any],
    input_data: dict[str, Any],
) -> dict[str, Any]:
    normalized_route = normalize_baidu_route(response, int(input_data.get("routeIndex") or 0))
    now = datetime.now(UTC).isoformat()
    route_context = {
        "routeId": input_data["id"],
        "destinationName": (input_data.get("destination") or {}).get("name") or "目的地",
        "origin": input_data.get("origin"),
        "destination": input_data.get("destination"),
    }
    route = {
        "id": input_data["id"],
        "name": input_data["name"],
        "elderSlot": input_data.get("elderSlot"),
        "origin": input_data.get("origin") or {},
        "destination": input_data.get("destination") or {},
        "travelModes": normalized_route["travelModes"],
        "status": "DRAFT",
        "lifecycleStatus": "DRAFT",
        "reviewLevel": "UNREVIEWED",
        "reviewedByUserId": "",
        "reviewedByName": "",
        "reviewedByRole": "",
        "reviewedAt": "",
        "version": int(input_data.get("version") or 1),
        "distance": normalized_route["distance"],
        "estimatedDuration": normalized_route["duration"],
        "sourceProvider": "BAIDU_MAP",
        "sourceRouteId": input_data.get("sourceRouteId") or "",
        "sourcePolyline": normalized_route["polyline"],
        "steps": extract_decision_points(normalized_route, route_context),
        "reviewSummary": None,
        "createdAt": input_data.get("createdAt") or now,
        "updatedAt": input_data.get("updatedAt") or now,
        "publishedAt": "",
    }
    return refresh_route_review(route, lambda: datetime.now(UTC).isoformat())
