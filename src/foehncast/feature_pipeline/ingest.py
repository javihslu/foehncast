"""Fetch weather data from Open-Meteo and MeteoSwiss APIs."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from foehncast.config import get_api_config, get_spots
from foehncast.env import env_value
from foehncast.http_client import ca_bundle

logger = logging.getLogger(__name__)

_TIMEOUT = 30  # seconds
# Retry transient Open-Meteo errors with a short backoff.
_session = requests.Session()
_session.mount(
    "https://",
    HTTPAdapter(
        max_retries=Retry(
            total=3, backoff_factor=2, status_forcelist=(429, 500, 502, 503, 504)
        )
    ),
)
_INGEST_FIXTURE_DIR_ENV = "FOEHNCAST_INGEST_FIXTURE_DIR"
_EXPECTED_HOURLY_UNITS = {
    "wind_speed_10m": "km/h",
    "wind_speed_80m": "km/h",
    "wind_speed_120m": "km/h",
    "wind_gusts_10m": "km/h",
}


def _get(url: str, params: dict[str, Any]) -> dict[str, Any]:
    """GET request with error handling."""
    resp = _session.get(url, params=params, timeout=_TIMEOUT, verify=ca_bundle())
    resp.raise_for_status()
    return resp.json()


def _hourly_params_csv(hourly_params: list[str]) -> str:
    """Join the configured hourly parameter list into Open-Meteo's comma-separated form."""
    return ",".join(hourly_params)


def _ingest_fixture_dir() -> Path | None:
    fixture_dir = env_value(_INGEST_FIXTURE_DIR_ENV)
    if not fixture_dir:
        return None

    return Path(fixture_dir)


def _validate_hourly_units(
    hourly: dict[str, Any], hourly_units: dict[str, Any]
) -> dict[str, str]:
    """Validate the upstream wind-unit contract for the hourly payload.

    Open-Meteo reports ``'undefined'`` as the unit metadata for some
    higher-altitude wind fields (80m, 120m) even when we explicitly
    request ``wind_speed_unit=kmh``.  We treat ``'undefined'`` as
    acceptable (with a warning) because we control the request parameter
    and the data values are still in km/h.
    """
    normalized_units = {key: str(value) for key, value in hourly_units.items()}

    for field, expected_unit in _EXPECTED_HOURLY_UNITS.items():
        if field not in hourly:
            continue

        actual_unit = normalized_units.get(field)
        if actual_unit == expected_unit:
            continue
        if actual_unit == "undefined":
            logger.warning(
                "Open-Meteo reports unit %r for %s; assuming %s "
                "(wind_speed_unit=kmh was requested)",
                actual_unit,
                field,
                expected_unit,
            )
            normalized_units[field] = expected_unit
            continue
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

    # Parse as UTC and convert; local wall-clock times are ambiguous
    # around DST changes.
    timestamps = pd.to_datetime(df["time"], utc=True)
    if timezone:
        timestamps = timestamps.dt.tz_convert(timezone)

    df["time"] = timestamps
    df = df.set_index("time")
    df.attrs["hourly_units"] = hourly_units
    return df


def fetch_forecast(
    lat: float,
    lon: float,
    *,
    past_days: int = 0,
    forecast_hours: int | None = None,
) -> pd.DataFrame:
    """Fetch forecast data for a location.

    Returns hourly weather data for the configured forecast horizon.
    A positive ``past_days`` also returns recent observed hours. With
    ``forecast_hours`` the window starts at the current hour instead of
    local midnight.
    """
    cfg = get_api_config()["open_meteo"]
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": _hourly_params_csv(cfg["hourly_params"]),
        "timezone": "UTC",
        "wind_speed_unit": cfg.get("wind_speed_unit", "kmh"),
    }
    if forecast_hours is not None:
        params["forecast_hours"] = forecast_hours
    else:
        params["forecast_days"] = cfg["forecast_days"]
    if past_days > 0:
        params["past_days"] = past_days
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
        "hourly": _hourly_params_csv(cfg["hourly_params"]),
        "start_date": start_date,
        "end_date": end_date,
        "timezone": "UTC",
        "wind_speed_unit": cfg.get("wind_speed_unit", "kmh"),
    }
    data = _get(cfg["archive_url"], params)
    return _hourly_to_dataframe(data, timezone=cfg["timezone"])


def fetch_spot(spot: dict[str, Any]) -> pd.DataFrame:
    """Fetch forecast data for a single spot, adding spot metadata columns."""
    fixture_dir = _ingest_fixture_dir()
    if fixture_dir is not None:
        fixture_path = fixture_dir / f"{spot['id']}.parquet"
        if not fixture_path.is_file():
            raise FileNotFoundError(
                f"Missing ingest fixture for {spot['id']}: {fixture_path}"
            )

        df = pd.read_parquet(fixture_path)
        if not isinstance(df.index, pd.DatetimeIndex):
            raise ValueError(
                f"Ingest fixture for {spot['id']} must use a DatetimeIndex"
            )

        if df.index.name is None:
            df.index.name = "time"

        hourly_units = {
            key: str(value)
            for key, value in dict(df.attrs.get("hourly_units", {})).items()
        }
        for field, expected_unit in _EXPECTED_HOURLY_UNITS.items():
            if field in df.columns:
                hourly_units.setdefault(field, expected_unit)
        df.attrs["hourly_units"] = hourly_units
    else:
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
