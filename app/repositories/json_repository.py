from pathlib import Path
from typing import Any

from app.storage import load_json, load_routes, save_json, save_routes


class JsonAppRepository:
    """File-backed repository used by the MVP deployment.

    The rest of the app depends on this small interface instead of raw JSON
    paths. That keeps the future SQLite/PostgreSQL migration isolated.
    """

    def __init__(
        self,
        *,
        route_config_file: Path,
        engine_routes_file: Path,
        trip_results_file: Path,
    ) -> None:
        self.route_config_file = route_config_file
        self.engine_routes_file = engine_routes_file
        self.trip_results_file = trip_results_file

    def load_route_configs(self) -> dict:
        return load_routes(self.route_config_file)

    def save_route_configs(self, routes: dict) -> None:
        save_routes(self.route_config_file, routes)

    def load_engine_routes(self) -> dict[str, Any]:
        return load_json(self.engine_routes_file, {})

    def save_engine_routes(self, routes: dict[str, Any]) -> None:
        save_json(self.engine_routes_file, routes)

    def load_trip_results(self) -> list[dict[str, Any]]:
        return load_json(self.trip_results_file, [])

    def save_trip_results(self, results: list[dict[str, Any]]) -> None:
        save_json(self.trip_results_file, results)
