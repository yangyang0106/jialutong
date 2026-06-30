import secrets
from threading import Lock
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException

from app.auth import family_guard, require_family_admin
from app.schemas import ArrivalEventUpdate, HelpEventUpdate, StepExecution
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

    def enrich_arrival_event(event: dict[str, Any], route: dict[str, Any]) -> dict[str, Any]:
        destination = route.get("destination") or {}
        return {
            **event,
            "routeName": route.get("name", ""),
            "destinationName": destination.get("name", ""),
            "elderSlot": route.get("elderSlot", ""),
            "elderId": route.get("elderId", ""),
        }

    def arrival_events_for_route(route_id: str, route: dict[str, Any]) -> list[dict[str, Any]]:
        events = [
            enrich_arrival_event(item, route)
            for item in load_trip_results()
            if item.get("routeId") == route_id and item.get("stepResult") == "ARRIVED"
        ]
        events.sort(key=lambda item: item.get("occurredAt", ""), reverse=True)
        return events

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
        if execution.get("stepResult") == "ARRIVED":
            if execution.get("arrivalStatus") in {None, "", "NONE"}:
                execution["arrivalStatus"] = "NOTIFIED"
            execution["arrivalNotifiedAt"] = execution.get("arrivalNotifiedAt") or execution["occurredAt"]
        else:
            execution["arrivalStatus"] = "NONE"
            execution["arrivalNotifiedAt"] = ""
        with trip_results_lock:
            executions = load_trip_results()
            executions.append(execution)
            save_trip_results(executions)
        return execution

    @router.get("/api/engine/arrival-events")
    def list_family_arrival_events(
        status: str | None = None,
        principal: dict[str, Any] = Depends(require_token),
    ) -> dict:
        routes = load_engine_routes()
        events: list[dict[str, Any]] = []
        for route_id, route in routes.items():
            if not family_guard(principal, route):
                continue
            events.extend(arrival_events_for_route(route_id, route))
        if status:
            events = [item for item in events if item.get("arrivalStatus") == status]
        events.sort(key=lambda item: item.get("occurredAt", ""), reverse=True)
        return {"events": events}

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

    @router.get("/api/engine/routes/{route_id}/arrival-events")
    def list_route_arrival_events(
        route_id: str,
        principal: dict[str, Any] = Depends(require_token),
    ) -> dict:
        route = load_engine_routes().get(route_id)
        if not route or not family_guard(principal, route):
            raise HTTPException(status_code=404, detail="route not found")
        return {"events": arrival_events_for_route(route_id, route)}

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
                    execution["handledByUserId"] = principal.get("id") or principal.get("userId", "")
                    execution["handledByName"] = principal.get("displayName", "")
                    execution["handledByRole"] = principal.get("role", "")
                    save_trip_results(executions)
                    return execution
        raise HTTPException(status_code=404, detail="help event not found")

    @router.put("/api/engine/routes/{route_id}/arrival-events/{event_id}")
    def update_route_arrival_event(
        route_id: str,
        event_id: str,
        update: ArrivalEventUpdate,
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
                    and execution.get("stepResult") == "ARRIVED"
                ):
                    execution["arrivalStatus"] = update.arrivalStatus
                    execution["acknowledgedNote"] = update.acknowledgedNote
                    if update.arrivalStatus == "ACKNOWLEDGED":
                        execution["acknowledgedAt"] = now_iso()
                        execution["acknowledgedByUserId"] = principal.get("id") or principal.get("userId", "")
                        execution["acknowledgedByName"] = principal.get("displayName", "")
                        execution["acknowledgedByRole"] = principal.get("role", "")
                    save_trip_results(executions)
                    return enrich_arrival_event(execution, route)
        raise HTTPException(status_code=404, detail="arrival event not found")

    @router.get("/api/engine/routes/{route_id}/trip-summary")
    def get_trip_summary(
        route_id: str,
        principal: dict[str, Any] = Depends(require_token),
    ) -> dict:
        trip_results = load_trip_results()
        executions = [item for item in trip_results if item.get("routeId") == route_id]
        summary = {"total": len(executions), "FOUND": 0, "NOT_FOUND": 0, "HELP": 0, "ARRIVED": 0}
        for execution in executions:
            result = execution.get("stepResult")
            if result in summary:
                summary[result] += 1
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
