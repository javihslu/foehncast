"""Fetch weather data from Open-Meteo and MeteoSwiss APIs."""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd
import requests

from foehncast.config import get_api_config, get_spots

logger = logging.getLogger(__name__)

_TIMEOUT = 30  # seconds


def _get(url: str, params: dict[str, Any]) -> dict[str, Any]:
    """GET request with error handling."""
    resp = requests.get(url, params=params, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def _hourly_to_dataframe(data: dict[str, Any]) -> pd.DataFrame:
    """Convert Open-Meteo hourly response to DataFrame."""
    hourly = data.get("hourly", {})
    if not hourly:
        return pd.DataFrame()
    df = pd.DataFrame(hourly)
    df["time"] = pd.to_datetime(df["time"])
    df = df.set_index("time")
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
    }
    data = _get(cfg["forecast_url"], params)
    return _hourly_to_dataframe(data)


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
    }
    data = _get(cfg["archive_url"], params)
    return _hourly_to_dataframe(data)


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
