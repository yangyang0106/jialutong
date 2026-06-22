from typing import Any, Callable
from urllib.parse import urlencode

from fastapi import HTTPException

from app.schemas import PlaceSearchRequest, ReverseGeocodeRequest, RoutePlanRequest


def is_station_transfer_walk(step: dict[str, Any]) -> bool:
    instruction = f"{step.get('instruction', '')}{step.get('instructions', '')}"
    return any(keyword in instruction for keyword in ("站内", "换乘", "通道"))


def request_baidu_walking_detail(
    start_location: dict[str, Any],
    end_location: dict[str, Any],
    *,
    api_key: str,
    request_json: Callable[[str], dict[str, Any]],
) -> list[dict[str, Any]]:
    if not start_location or not end_location:
        return []
    params = {
        "origin": f"{start_location.get('lat')},{start_location.get('lng')}",
        "destination": f"{end_location.get('lat')},{end_location.get('lng')}",
        "ak": api_key,
        "output": "json",
        "coord_type": "gcj02",
        "ret_coordtype": "gcj02",
    }
    url = f"https://api.map.baidu.com/directionlite/v1/walking?{urlencode(params)}"
    result = request_json(url)
    routes = (result.get("result") or {}).get("routes") or []
    return routes[0].get("steps", []) if routes else []


def enrich_transit_walking_steps(
    result: dict[str, Any],
    *,
    api_key: str,
    request_json: Callable[[str], dict[str, Any]],
) -> dict[str, Any]:
    routes = (result.get("result") or {}).get("routes") or []
    if not routes:
        return result
    for route in routes:
        enriched_groups = []
        for group in route.get("steps", []):
            source_steps = group if isinstance(group, list) else [group]
            enriched_steps = []
            for step in source_steps:
                if int(step.get("type") or 0) != 5 or is_station_transfer_walk(step):
                    enriched_steps.append(step)
                    continue
                try:
                    detail_steps = request_baidu_walking_detail(
                        step.get("start_location") or {},
                        step.get("end_location") or {},
                        api_key=api_key,
                        request_json=request_json,
                    )
                except HTTPException:
                    detail_steps = []
                enriched_steps.extend(detail_steps or [step])
            enriched_groups.append(enriched_steps)
        route["steps"] = enriched_groups
    return result


def request_baidu_route_plan(
    route_request: RoutePlanRequest,
    *,
    api_key: str,
    request_json: Callable[[str], dict[str, Any]],
) -> dict[str, Any]:
    if not api_key:
        raise HTTPException(status_code=503, detail="请先配置百度地图服务端 AK")
    if (
        route_request.origin.latitude is None
        or route_request.origin.longitude is None
        or route_request.destination.latitude is None
        or route_request.destination.longitude is None
    ):
        raise HTTPException(status_code=400, detail="origin and destination are required")
    route_mode = "walking" if route_request.mode == "WALKING" else "transit"
    params = {
        "origin": f"{route_request.origin.latitude},{route_request.origin.longitude}",
        "destination": f"{route_request.destination.latitude},{route_request.destination.longitude}",
        "ak": api_key,
        "output": "json",
        "coord_type": "gcj02",
        "ret_coordtype": "gcj02",
    }
    if route_request.mode == "TRANSIT":
        params["tactics_incity"] = "0"
    url = f"https://api.map.baidu.com/directionlite/v1/{route_mode}?{urlencode(params)}"
    result = request_json(url)
    return (
        enrich_transit_walking_steps(result, api_key=api_key, request_json=request_json)
        if route_request.mode == "TRANSIT"
        else result
    )


def request_baidu_place_search(
    search_request: PlaceSearchRequest,
    *,
    api_key: str,
    request_json: Callable[[str], dict[str, Any]],
) -> dict[str, Any]:
    if not api_key:
        raise HTTPException(status_code=503, detail="请先配置百度地图服务端 AK")
    keyword = search_request.keyword.strip()
    if not keyword:
        raise HTTPException(status_code=400, detail="keyword is required")
    params = {
        "query": keyword,
        "region": search_request.region,
        "city_limit": "true",
        "ak": api_key,
        "output": "json",
        "page_size": 10,
        "ret_coordtype": "gcj02ll",
    }
    url = f"https://api.map.baidu.com/place/v2/search?{urlencode(params)}"
    result = request_json(url)
    return {
        "places": [
            {
                "id": item.get("uid", ""),
                "name": item.get("name", ""),
                "address": item.get("address", ""),
                "latitude": (item.get("location") or {}).get("lat"),
                "longitude": (item.get("location") or {}).get("lng"),
            }
            for item in result.get("results", [])
        ]
    }


def request_baidu_reverse_geocode(
    reverse_request: ReverseGeocodeRequest,
    *,
    api_key: str,
    request_json: Callable[[str], dict[str, Any]],
) -> dict[str, Any]:
    if not api_key:
        raise HTTPException(status_code=503, detail="请先配置百度地图服务端 AK")
    location = reverse_request.location
    if location.latitude is None or location.longitude is None:
        raise HTTPException(status_code=400, detail="当前位置坐标不完整")
    params = {
        "location": f"{location.latitude},{location.longitude}",
        "coordtype": "gcj02ll",
        "ret_coordtype": "gcj02ll",
        "extensions_poi": 1,
        "latest_admin": 1,
        "ak": api_key,
        "output": "json",
    }
    url = f"https://api.map.baidu.com/reverse_geocoding/v3/?{urlencode(params)}"
    result = request_json(url).get("result") or {}
    pois = result.get("pois") or []
    primary_poi = pois[0] if pois else {}
    address_component = result.get("addressComponent") or {}
    name = (
        primary_poi.get("name")
        or address_component.get("street")
        or result.get("formatted_address")
        or "已定位地点"
    )
    return {
        "place": {
            "id": primary_poi.get("uid", ""),
            "name": name,
            "poiName": primary_poi.get("name", ""),
            "communityName": primary_poi.get("addr", ""),
            "address": result.get("formatted_address", ""),
            "detailAddress": result.get("sematic_description", ""),
            "latitude": location.latitude,
            "longitude": location.longitude,
        }
    }
