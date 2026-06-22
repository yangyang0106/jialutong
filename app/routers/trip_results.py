from threading import Lock
from typing import Any, Callable

from fastapi import APIRouter, Depends

from app.schemas import StepExecution
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

    @router.post("/api/engine/trip-results", dependencies=[Depends(require_token)])
    def create_trip_result(execution_input: StepExecution) -> dict:
        execution = execution_input.model_dump()
        execution["occurredAt"] = execution.get("occurredAt") or now_iso()
        with trip_results_lock:
            executions = load_trip_results()
            executions.append(execution)
            save_trip_results(executions)
        return execution

    @router.get("/api/engine/routes/{route_id}/trip-summary")
    def get_trip_summary(route_id: str) -> dict:
        trip_results = load_trip_results()
        executions = [item for item in trip_results if item.get("routeId") == route_id]
        summary = {"total": len(executions), "FOUND": 0, "NOT_FOUND": 0, "HELP": 0}
        for execution in executions:
            summary[execution["stepResult"]] += 1
        route = load_engine_routes().get(route_id)
        if not route:
            return {"routeId": route_id, "summary": summary}
        center = build_route_review_center(normalize_route_voices(route), trip_results)
        return {
            **center,
            "summary": summary,
        }

    return router
