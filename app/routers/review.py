from threading import Lock
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException

from app.schemas import PhotoReviewRequest
from app.services.voice import normalize_route_voices


def create_review_router(
    *,
    require_token,
    engine_routes_lock: Lock,
    load_engine_routes: Callable[[], dict[str, Any]],
    save_engine_routes: Callable[[dict[str, Any]], None],
    load_trip_results: Callable[[], list[dict[str, Any]]],
    refresh_route_review: Callable[[dict[str, Any]], dict[str, Any]],
    build_route_review_center,
    analyze_trip_failures,
    review_step_photo,
    ai_config: Callable[[], dict[str, Any]],
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/engine/routes/{route_id}/review-center")
    def get_route_review_center(route_id: str) -> dict:
        route = load_engine_routes().get(route_id)
        if not route:
            raise HTTPException(status_code=404, detail="route not found")
        return build_route_review_center(normalize_route_voices(route), load_trip_results())

    @router.post(
        "/api/engine/routes/{route_id}/trip-analysis",
        dependencies=[Depends(require_token)],
    )
    def analyze_route_trip(route_id: str) -> dict:
        route = load_engine_routes().get(route_id)
        if not route:
            raise HTTPException(status_code=404, detail="route not found")
        route = normalize_route_voices(route)
        review_center = build_route_review_center(route, load_trip_results())
        return analyze_trip_failures(route, review_center, **ai_config())

    @router.post(
        "/api/engine/routes/{route_id}/steps/{step_id}/photo-review",
        dependencies=[Depends(require_token)],
    )
    def review_engine_route_step_photo(
        route_id: str, step_id: str, photo_request: PhotoReviewRequest
    ) -> dict:
        with engine_routes_lock:
            routes = load_engine_routes()
            route = routes.get(route_id)
            if not route:
                raise HTTPException(status_code=404, detail="route not found")
            if route.get("status") == "PUBLISHED":
                raise HTTPException(status_code=409, detail="published route is immutable")
            step = next((item for item in route["steps"] if item["id"] == step_id), None)
            if not step:
                raise HTTPException(status_code=404, detail="step not found")
            result = review_step_photo(
                step,
                image_url=photo_request.imageUrl,
                image_status=photo_request.imageStatus,
                file_size=photo_request.fileSize,
            )
            step["photoReview"] = result
            route = refresh_route_review(route)
            routes[route_id] = route
            save_engine_routes(routes)
        return {"route": route, "photoReview": result}

    return router
