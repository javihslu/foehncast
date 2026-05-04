"""OSRM distance and drive time calculations from rider location."""

from __future__ import annotations

from typing import Any

import requests

from foehncast.config import get_api_config

_TIMEOUT = 30


def get_drive_minutes(
    origin_lat: float,
    origin_lon: float,
    destination_lat: float,
    destination_lon: float,
) -> float:
    """Return the OSRM drive time in minutes between two coordinates."""
    base_url = get_api_config()["osrm"]["base_url"].rstrip("/")
    url = f"{base_url}/{origin_lon},{origin_lat};{destination_lon},{destination_lat}"
    response = requests.get(url, params={"overview": "false"}, timeout=_TIMEOUT)
    response.raise_for_status()

    routes = response.json().get("routes", [])
    if not routes:
        raise ValueError("OSRM did not return a route")

    return float(routes[0]["duration"]) / 60.0


def get_drive_minutes_to_spot(
    spot: dict[str, Any], rider_config: dict[str, Any]
) -> float:
    """Return the OSRM drive time in minutes from the rider's home to a spot."""
    return get_drive_minutes(
        origin_lat=rider_config["home_lat"],
        origin_lon=rider_config["home_lon"],
        destination_lat=spot["lat"],
        destination_lon=spot["lon"],
    )
