from typing import Any, Protocol


class EngineRouteRepository(Protocol):
    def load_engine_routes(self) -> dict[str, Any]:
        ...

    def save_engine_routes(self, routes: dict[str, Any]) -> None:
        ...


class TripResultRepository(Protocol):
    def load_trip_results(self) -> list[dict[str, Any]]:
        ...

    def save_trip_results(self, results: list[dict[str, Any]]) -> None:
        ...


class AppRepository(EngineRouteRepository, TripResultRepository, Protocol):
    """Repository contract used by routers and services.

    JSON is the current MVP implementation. SQLite/PostgreSQL can replace it
    later without changing route, review or trip-result routers.
    """
