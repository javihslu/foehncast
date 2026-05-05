"""Fetch weather data from Open-Meteo and MeteoSwiss APIs."""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd
import requests

from foehncast.config import get_api_config, get_spots
from foehncast.http_client import ca_bundle

logger = logging.getLogger(__name__)

_TIMEOUT = 30  # seconds
_EXPECTED_HOURLY_UNITS = {
    "wind_speed_10m": "km/h",
    "wind_speed_80m": "km/h",
    "wind_speed_120m": "km/h",
    "wind_gusts_10m": "km/h",
}


def _get(url: str, params: dict[str, Any]) -> dict[str, Any]:
    """GET request with error handling."""
    resp = requests.get(url, params=params, timeout=_TIMEOUT, verify=ca_bundle())
    resp.raise_for_status()
    return resp.json()


def _validate_hourly_units(
    hourly: dict[str, Any], hourly_units: dict[str, Any]
) -> dict[str, str]:
    """Validate the upstream wind-unit contract for the hourly payload."""
    normalized_units = {key: str(value) for key, value in hourly_units.items()}

    for field, expected_unit in _EXPECTED_HOURLY_UNITS.items():
        if field not in hourly:
            continue

        actual_unit = normalized_units.get(field)
        if actual_unit != expected_unit:
            raise ValueError(
                f"Unexpected unit for {field}: expected {expected_unit}, got {actual_unit!r}"
            )

    return normalized_units


def _hourly_to_dataframe(
    data: dict[str, Any], timezone: str | None = None
) -> pd.DataFrame:
    """Convert Open-Meteo hourly response to DataFrame."""
    hourly = data.get("hourly", {})
    if not hourly:
        return pd.DataFrame()

    hourly_units = _validate_hourly_units(hourly, data.get("hourly_units", {}))

    df = pd.DataFrame(hourly)

    timestamps = pd.to_datetime(df["time"])
    if timezone:
        if timestamps.dt.tz is None:
            timestamps = timestamps.dt.tz_localize(timezone)
        else:
            timestamps = timestamps.dt.tz_convert(timezone)

    df["time"] = timestamps
    df = df.set_index("time")
    df.attrs["hourly_units"] = hourly_units
    return df


def fetch_forecast(lat: float, lon: float) -> pd.DataFrame:
    """Fetch forecast data for a location.

    Returns hourly weather data for the configured forecast horizon.
    """
    cfg = get_api_config()["open_meteo"]
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": cfg["hourly_params"],
        "forecast_days": cfg["forecast_days"],
        "timezone": cfg["timezone"],
        "wind_speed_unit": cfg.get("wind_speed_unit", "kmh"),
    }
    data = _get(cfg["forecast_url"], params)
    return _hourly_to_dataframe(data, timezone=cfg["timezone"])


def fetch_archive(
    lat: float, lon: float, start_date: str, end_date: str
) -> pd.DataFrame:
    """Fetch historical weather data for a location.

    Args:
        lat: Latitude.
        lon: Longitude.
        start_date: ISO format date string (YYYY-MM-DD).
        end_date: ISO format date string (YYYY-MM-DD).
    """
    cfg = get_api_config()["open_meteo"]
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": cfg["hourly_params"],
        "start_date": start_date,
        "end_date": end_date,
        "timezone": cfg["timezone"],
        "wind_speed_unit": cfg.get("wind_speed_unit", "kmh"),
    }
    data = _get(cfg["archive_url"], params)
    return _hourly_to_dataframe(data, timezone=cfg["timezone"])


def fetch_spot(spot: dict[str, Any]) -> pd.DataFrame:
    """Fetch forecast data for a single spot, adding spot metadata columns."""
    df = fetch_forecast(spot["lat"], spot["lon"])
    if df.empty:
        return df
    df["spot_id"] = spot["id"]
    df["spot_name"] = spot["name"]
    return df


def fetch_all_spots() -> dict[str, pd.DataFrame]:
    """Fetch forecast data for all configured spots.

    Returns:
        Dict mapping spot_id to its forecast DataFrame.
    """
    spots = get_spots()
    results: dict[str, pd.DataFrame] = {}
    for spot in spots:
        logger.info("Fetching forecast for %s", spot["id"])
        try:
            results[spot["id"]] = fetch_spot(spot)
        except requests.RequestException:
            logger.exception("Failed to fetch %s", spot["id"])
    return results
