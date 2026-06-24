import secrets
from threading import Lock
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException

from app.auth import family_guard, require_family_admin
from app.schemas import HelpEventUpdate, StepExecution
from app.services.voice import normalize_route_voices


def create_trip_results_router(
    *,
    require_token,
    trip_results_lock: Lock,
    load_engine_routes: Callable[[], dict[str, Any]],
    load_trip_results: Callable[[], list[dict[str, Any]]],
    save_trip_results: Callable[[list[dict[str, Any]]], None],
    build_route_review_center: Callable[[dict[str, Any], list[dict[str, Any]]], dict[str, Any]],
    now_iso: Callable[[], str],
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/engine/trip-results")
    def create_trip_result(
        execution_input: StepExecution,
        principal: dict[str, Any] = Depends(require_token),
    ) -> dict:
        execution = execution_input.model_dump()
        route = load_engine_routes().get(execution["routeId"])
        if route and not family_guard(principal, route):
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="route not found")
        execution["id"] = execution.get("id") or f"trip-result-{secrets.token_hex(8)}"
        execution["occurredAt"] = execution.get("occurredAt") or now_iso()
        if execution.get("stepResult") == "HELP":
            if execution.get("helpStatus") in {None, "", "NONE"}:
                execution["helpStatus"] = "REQUESTED"
        else:
            execution["helpStatus"] = "NONE"
        with trip_results_lock:
            executions = load_trip_results()
            executions.append(execution)
            save_trip_results(executions)
        return execution


    @router.get("/api/engine/routes/{route_id}/help-events")
    def list_route_help_events(
        route_id: str,
        principal: dict[str, Any] = Depends(require_token),
    ) -> dict:
        route = load_engine_routes().get(route_id)
        if not route or not family_guard(principal, route):
            raise HTTPException(status_code=404, detail="route not found")
        events = [
            item
            for item in load_trip_results()
            if item.get("routeId") == route_id and item.get("stepResult") == "HELP"
        ]
        events.sort(key=lambda item: item.get("occurredAt", ""), reverse=True)
        return {"events": events}

    @router.put("/api/engine/routes/{route_id}/help-events/{event_id}")
    def update_route_help_event(
        route_id: str,
        event_id: str,
        update: HelpEventUpdate,
        principal: dict[str, Any] = Depends(require_token),
    ) -> dict:
        require_family_admin(principal)
        route = load_engine_routes().get(route_id)
        if not route or not family_guard(principal, route):
            raise HTTPException(status_code=404, detail="route not found")
        with trip_results_lock:
            executions = load_trip_results()
            for execution in executions:
                if (
                    execution.get("id") == event_id
                    and execution.get("routeId") == route_id
                    and execution.get("stepResult") == "HELP"
                ):
                    execution["helpStatus"] = update.helpStatus
                    execution["handledNote"] = update.handledNote
                    execution["handledAt"] = now_iso()
                    execution["handledByUserId"] = principal.get("userId", "")
                    execution["handledByName"] = principal.get("displayName", "")
                    execution["handledByRole"] = principal.get("role", "")
                    save_trip_results(executions)
                    return execution
        raise HTTPException(status_code=404, detail="help event not found")

    @router.get("/api/engine/routes/{route_id}/trip-summary")
    def get_trip_summary(
        route_id: str,
        principal: dict[str, Any] = Depends(require_token),
    ) -> dict:
        trip_results = load_trip_results()
        executions = [item for item in trip_results if item.get("routeId") == route_id]
        summary = {"total": len(executions), "FOUND": 0, "NOT_FOUND": 0, "HELP": 0}
        for execution in executions:
            summary[execution["stepResult"]] += 1
        route = load_engine_routes().get(route_id)
        if not route:
            raise HTTPException(status_code=404, detail="route not found")
        if not family_guard(principal, route):
            raise HTTPException(status_code=404, detail="route not found")
        center = build_route_review_center(normalize_route_voices(route), trip_results)
        return {
            **center,
            "summary": summary,
        }

    return router
