from threading import Lock
from typing import Any, Callable, Literal

from fastapi import APIRouter, Depends, HTTPException

from app.schemas import EngineRoute, StepReview
from app.services.voice import normalize_route_voices


def create_routes_router(
    *,
    require_token,
    engine_routes_lock: Lock,
    load_engine_routes: Callable[[], dict[str, Any]],
    save_engine_routes: Callable[[dict[str, Any]], None],
    now_iso: Callable[[], str],
    refresh_route_review: Callable[[dict[str, Any]], dict[str, Any]],
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/engine/routes")
    def list_engine_routes(status: str | None = None) -> dict:
        routes = list(load_engine_routes().values())
        if status:
            routes = [route for route in routes if route.get("status") == status]
        return {"routes": routes}

    @router.get("/api/engine/elder-routes/{slot}")
    def get_published_elder_route(slot: Literal["TO_MOM", "TO_HOME"]) -> dict:
        routes = [
            route
            for route in load_engine_routes().values()
            if route.get("status") == "PUBLISHED" and route.get("elderSlot") == slot
        ]
        if not routes:
            raise HTTPException(status_code=404, detail="published elder route not found")
        return max(
            routes,
            key=lambda route: route.get("publishedAt") or route.get("updatedAt") or "",
        )

    @router.post("/api/engine/routes", dependencies=[Depends(require_token)])
    def create_engine_route(route_input: EngineRoute) -> dict:
        route = route_input.model_dump()
        route["createdAt"] = route.get("createdAt") or now_iso()
        route["publishedAt"] = ""
        route = refresh_route_review(route)
        with engine_routes_lock:
            routes = load_engine_routes()
            if route["id"] in routes:
                raise HTTPException(status_code=409, detail="route already exists")
            routes[route["id"]] = route
            save_engine_routes(routes)
        return route

    @router.get("/api/engine/routes/{route_id}")
    def get_engine_route(route_id: str) -> dict:
        route = load_engine_routes().get(route_id)
        if not route:
            raise HTTPException(status_code=404, detail="route not found")
        return normalize_route_voices(route)

    @router.put("/api/engine/routes/{route_id}", dependencies=[Depends(require_token)])
    def update_engine_route(route_id: str, route_input: EngineRoute) -> dict:
        if route_id != route_input.id:
            raise HTTPException(status_code=400, detail="route id mismatch")
        with engine_routes_lock:
            routes = load_engine_routes()
            current = routes.get(route_id)
            if not current:
                raise HTTPException(status_code=404, detail="route not found")
            if current.get("status") == "PUBLISHED":
                raise HTTPException(status_code=409, detail="published route is immutable")
            route = route_input.model_dump()
            route["createdAt"] = current.get("createdAt") or now_iso()
            route = refresh_route_review(route)
            routes[route_id] = route
            save_engine_routes(routes)
        return route

    @router.delete("/api/engine/routes/{route_id}", dependencies=[Depends(require_token)])
    def delete_engine_route(route_id: str) -> dict[str, bool]:
        with engine_routes_lock:
            routes = load_engine_routes()
            route = routes.get(route_id)
            if not route:
                raise HTTPException(status_code=404, detail="route not found")
            if route.get("status") == "PUBLISHED":
                raise HTTPException(status_code=409, detail="published route cannot be deleted")
            del routes[route_id]
            save_engine_routes(routes)
        return {"deleted": True}

    @router.put(
        "/api/engine/routes/{route_id}/steps/{step_id}/review",
        dependencies=[Depends(require_token)],
    )
    def review_engine_route_step(route_id: str, step_id: str, review: StepReview) -> dict:
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
            step.update(review.model_dump(exclude_none=True))
            if review.reviewStatus == "APPROVED":
                step["requiresFamilyReview"] = False
                step["needsReview"] = False
            route = refresh_route_review(route)
            routes[route_id] = route
            save_engine_routes(routes)
        return route

    @router.post("/api/engine/routes/{route_id}/publish", dependencies=[Depends(require_token)])
    def publish_engine_route(route_id: str) -> dict:
        with engine_routes_lock:
            routes = load_engine_routes()
            route = routes.get(route_id)
            if not route:
                raise HTTPException(status_code=404, detail="route not found")
            route = refresh_route_review(route)
            if not route["reviewSummary"]["ready"]:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": "route is not ready",
                        "blockingSteps": route["reviewSummary"]["blockingSteps"],
                    },
                )
            route["status"] = "PUBLISHED"
            route["version"] = int(route.get("version") or 1)
            route["publishedAt"] = now_iso()
            route["updatedAt"] = route["publishedAt"]
            for existing_id, existing_route in routes.items():
                if (
                    existing_id != route_id
                    and existing_route.get("status") == "PUBLISHED"
                    and existing_route.get("elderSlot") == route.get("elderSlot")
                ):
                    existing_route["status"] = "DISABLED"
                    existing_route["updatedAt"] = route["publishedAt"]
            routes[route_id] = route
            save_engine_routes(routes)
        return route

    @router.post("/api/engine/routes/{route_id}/disable", dependencies=[Depends(require_token)])
    def disable_engine_route(route_id: str) -> dict:
        with engine_routes_lock:
            routes = load_engine_routes()
            route = routes.get(route_id)
            if not route:
                raise HTTPException(status_code=404, detail="route not found")
            route["status"] = "DISABLED"
            route["updatedAt"] = now_iso()
            routes[route_id] = route
            save_engine_routes(routes)
        return route

    return router
