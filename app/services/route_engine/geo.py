import math
from typing import Any


EARTH_RADIUS_METERS = 6_371_000


def calculate_distance(
    from_latitude: float,
    from_longitude: float,
    to_latitude: float,
    to_longitude: float,
) -> int:
    latitude_delta = math.radians(to_latitude - from_latitude)
    longitude_delta = math.radians(to_longitude - from_longitude)
    from_latitude_radians = math.radians(from_latitude)
    to_latitude_radians = math.radians(to_latitude)
    haversine = (
        math.sin(latitude_delta / 2) ** 2
        + math.cos(from_latitude_radians)
        * math.cos(to_latitude_radians)
        * math.sin(longitude_delta / 2) ** 2
    )
    return round(
        EARTH_RADIUS_METERS
        * 2
        * math.atan2(math.sqrt(haversine), math.sqrt(1 - haversine))
    )


def normalize_location(location: Any) -> dict[str, float] | None:
    if not isinstance(location, dict):
        return None
    latitude = location.get("latitude", location.get("lat"))
    longitude = location.get("longitude", location.get("lng"))
    if latitude is None or longitude is None:
        return None
    try:
        return {"latitude": float(latitude), "longitude": float(longitude)}
    except (TypeError, ValueError):
        return None
