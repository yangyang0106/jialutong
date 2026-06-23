from threading import Lock
from typing import Any, Callable, Literal

from fastapi import APIRouter, Depends, HTTPException

from app.auth import family_guard, route_owner_patch
from app.schemas import EngineRoute, StepReview
from app.services.voice import normalize_route_voices


def _require_family_admin(principal: dict[str, Any]) -> None:
    if principal.get("authType") == "LEGACY_TOKEN":
        return
    if principal.get("role") != "FAMILY_ADMIN":
        raise HTTPException(status_code=403, detail="只有家庭管理员可以管理路线")


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
    def list_engine_routes(
        status: str | None = None,
        principal: dict[str, Any] = Depends(require_token),
    ) -> dict:
        routes = list(load_engine_routes().values())
        routes = [route for route in routes if family_guard(principal, route)]
        if status:
            routes = [route for route in routes if route.get("status") == status]
        return {"routes": routes}

    @router.get("/api/engine/elder-routes/{slot}")
    def get_published_elder_route(
        slot: Literal["TO_MOM", "TO_HOME"],
        principal: dict[str, Any] = Depends(require_token),
    ) -> dict:
        routes = [
            route
            for route in load_engine_routes().values()
            if route.get("status") == "PUBLISHED"
            and route.get("elderSlot") == slot
            and family_guard(principal, route)
            and (
                principal.get("authType") == "LEGACY_TOKEN"
                or not route.get("elderId")
                or route.get("elderId") in set(principal.get("accessibleElderIds") or [])
            )
        ]
        if not routes:
            raise HTTPException(status_code=404, detail="published elder route not found")
        return max(
            routes,
            key=lambda route: route.get("publishedAt") or route.get("updatedAt") or "",
        )

    @router.post("/api/engine/routes")
    def create_engine_route(
        route_input: EngineRoute,
        principal: dict[str, Any] = Depends(require_token),
    ) -> dict:
        route = route_input.model_dump()
        route.update(route_owner_patch(principal, route))
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
    def get_engine_route(
        route_id: str,
        principal: dict[str, Any] | None = Depends(require_token),
    ) -> dict:
        route = load_engine_routes().get(route_id)
        if not route:
            raise HTTPException(status_code=404, detail="route not found")
        if route.get("status") != "PUBLISHED" and not family_guard(principal, route):
            raise HTTPException(status_code=404, detail="route not found")
        return normalize_route_voices(route)

    @router.put("/api/engine/routes/{route_id}")
    def update_engine_route(
        route_id: str,
        route_input: EngineRoute,
        principal: dict[str, Any] = Depends(require_token),
    ) -> dict:
        _require_family_admin(principal)
        if route_id != route_input.id:
            raise HTTPException(status_code=400, detail="route id mismatch")
        with engine_routes_lock:
            routes = load_engine_routes()
            current = routes.get(route_id)
            if not current:
                raise HTTPException(status_code=404, detail="route not found")
            if not family_guard(principal, current):
                raise HTTPException(status_code=404, detail="route not found")
            if current.get("status") == "PUBLISHED":
                raise HTTPException(status_code=409, detail="published route is immutable")
            route = route_input.model_dump()
            route.update(route_owner_patch(principal, route))
            route["createdAt"] = current.get("createdAt") or now_iso()
            route = refresh_route_review(route)
            routes[route_id] = route
            save_engine_routes(routes)
        return route

    @router.delete("/api/engine/routes/{route_id}")
    def delete_engine_route(
        route_id: str,
        principal: dict[str, Any] = Depends(require_token),
    ) -> dict[str, bool]:
        _require_family_admin(principal)
        with engine_routes_lock:
            routes = load_engine_routes()
            route = routes.get(route_id)
            if not route:
                raise HTTPException(status_code=404, detail="route not found")
            if not family_guard(principal, route):
                raise HTTPException(status_code=404, detail="route not found")
            if route.get("status") == "PUBLISHED":
                raise HTTPException(status_code=409, detail="published route cannot be deleted")
            del routes[route_id]
            save_engine_routes(routes)
        return {"deleted": True}

    @router.put(
        "/api/engine/routes/{route_id}/steps/{step_id}/review",
    )
    def review_engine_route_step(
        route_id: str,
        step_id: str,
        review: StepReview,
        principal: dict[str, Any] = Depends(require_token),
    ) -> dict:
        _require_family_admin(principal)
        with engine_routes_lock:
            routes = load_engine_routes()
            route = routes.get(route_id)
            if not route:
                raise HTTPException(status_code=404, detail="route not found")
            if not family_guard(principal, route):
                raise HTTPException(status_code=404, detail="route not found")
            if route.get("status") == "PUBLISHED":
                raise HTTPException(status_code=409, detail="published route is immutable")
            step = next((item for item in route["steps"] if item["id"] == step_id), None)
            if not step:
                raise HTTPException(status_code=404, detail="step not found")
            step.update(review.model_dump(exclude_none=True))
            if review.reviewStatus:
                step["reviewedByUserId"] = principal.get("id") or principal.get("userId") or ""
                step["reviewedByName"] = principal.get("displayName") or principal.get("username") or "家庭管理员"
                step["reviewedByRole"] = principal.get("role") or "ADMIN"
                step["reviewedAt"] = now_iso()
            if review.reviewStatus == "APPROVED":
                step["requiresFamilyReview"] = False
                step["needsReview"] = False
            route = refresh_route_review(route)
            routes[route_id] = route
            save_engine_routes(routes)
        return route

    @router.post("/api/engine/routes/{route_id}/publish")
    def publish_engine_route(
        route_id: str,
        principal: dict[str, Any] = Depends(require_token),
    ) -> dict:
        _require_family_admin(principal)
        with engine_routes_lock:
            routes = load_engine_routes()
            route = routes.get(route_id)
            if not route:
                raise HTTPException(status_code=404, detail="route not found")
            if not family_guard(principal, route):
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
            route["lifecycleStatus"] = "PUBLISHED"
            route["reviewLevel"] = "GUARDIAN_REVIEWED"
            route["reviewedByUserId"] = principal.get("id") or principal.get("userId") or ""
            route["reviewedByName"] = principal.get("displayName") or principal.get("username") or "家庭管理员"
            route["reviewedByRole"] = principal.get("role") or "ADMIN"
            route["reviewedAt"] = now_iso()
            route["version"] = int(route.get("version") or 1)
            route["publishedAt"] = route["reviewedAt"]
            route["updatedAt"] = route["publishedAt"]
            for existing_id, existing_route in routes.items():
                if (
                    existing_id != route_id
                    and existing_route.get("status") == "PUBLISHED"
                    and existing_route.get("elderSlot") == route.get("elderSlot")
                    and existing_route.get("familyId") == route.get("familyId")
                    and existing_route.get("elderId") == route.get("elderId")
                ):
                    existing_route["status"] = "DISABLED"
                    existing_route["lifecycleStatus"] = "DISABLED"
                    existing_route["updatedAt"] = route["publishedAt"]
            routes[route_id] = route
            save_engine_routes(routes)
        return route

    @router.post("/api/engine/routes/{route_id}/disable")
    def disable_engine_route(
        route_id: str,
        principal: dict[str, Any] = Depends(require_token),
    ) -> dict:
        _require_family_admin(principal)
        with engine_routes_lock:
            routes = load_engine_routes()
            route = routes.get(route_id)
            if not route:
                raise HTTPException(status_code=404, detail="route not found")
            if not family_guard(principal, route):
                raise HTTPException(status_code=404, detail="route not found")
            route["status"] = "DISABLED"
            route["lifecycleStatus"] = "DISABLED"
            route["updatedAt"] = now_iso()
            routes[route_id] = route
            save_engine_routes(routes)
        return route

    return router
