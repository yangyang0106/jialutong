from typing import Callable

from fastapi import APIRouter, Depends

from app.schemas import (
    PlaceSearchRequest,
    ReverseGeocodeRequest,
    RouteAdviceRequest,
    RoutePlanRequest,
)


def create_planning_router(
    *,
    require_token,
    request_baidu_route_plan: Callable[[RoutePlanRequest], dict],
    request_baidu_place_search: Callable[[PlaceSearchRequest], dict],
    request_baidu_reverse_geocode: Callable[[ReverseGeocodeRequest], dict],
    advise_engine_routes: Callable[[RouteAdviceRequest], dict],
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/engine/route-plans", dependencies=[Depends(require_token)])
    def create_route_plan(route_request: RoutePlanRequest) -> dict:
        return request_baidu_route_plan(route_request)

    @router.post("/api/engine/routes/advise", dependencies=[Depends(require_token)])
    def advise_routes(advice_request: RouteAdviceRequest) -> dict:
        return advise_engine_routes(advice_request)

    @router.post("/api/engine/places/search", dependencies=[Depends(require_token)])
    def search_places(search_request: PlaceSearchRequest) -> dict:
        return request_baidu_place_search(search_request)

    @router.post("/api/engine/places/reverse-geocode", dependencies=[Depends(require_token)])
    def reverse_geocode(reverse_request: ReverseGeocodeRequest) -> dict:
        return request_baidu_reverse_geocode(reverse_request)

    return router
