"""Solar position helpers for daylight-aware rendering and metrics."""

from __future__ import annotations

import numpy as np
import pandas as pd

# Sun center sits 0.833 deg below the horizon at sunrise/sunset once
# atmospheric refraction is accounted for.
_HORIZON_DEG = -0.833


def solar_elevation_deg(lat: float, lon: float, times: pd.DatetimeIndex) -> pd.Series:
    """Solar elevation angle in degrees for tz-aware times at a location.

    Uses the NOAA low-accuracy approximation, good to a fraction of a degree.
    """
    utc = times.tz_convert("UTC")
    day_of_year = utc.dayofyear.to_numpy()
    hour_frac = (
        utc.hour.to_numpy()
        + utc.minute.to_numpy() / 60.0
        + utc.second.to_numpy() / 3600.0
    )

    gamma = 2.0 * np.pi / 365.0 * (day_of_year - 1 + (hour_frac - 12.0) / 24.0)
    eqtime_min = 229.18 * (
        0.000075
        + 0.001868 * np.cos(gamma)
        - 0.032077 * np.sin(gamma)
        - 0.014615 * np.cos(2 * gamma)
        - 0.040849 * np.sin(2 * gamma)
    )
    decl = (
        0.006918
        - 0.399912 * np.cos(gamma)
        + 0.070257 * np.sin(gamma)
        - 0.006758 * np.cos(2 * gamma)
        + 0.000907 * np.sin(2 * gamma)
        - 0.002697 * np.cos(3 * gamma)
        + 0.00148 * np.sin(3 * gamma)
    )

    true_solar_min = hour_frac * 60.0 + eqtime_min + 4.0 * lon
    hour_angle = np.radians(true_solar_min / 4.0 - 180.0)
    lat_rad = np.radians(lat)
    cos_zenith = np.sin(lat_rad) * np.sin(decl) + np.cos(lat_rad) * np.cos(
        decl
    ) * np.cos(hour_angle)
    elevation = 90.0 - np.degrees(np.arccos(np.clip(cos_zenith, -1.0, 1.0)))
    return pd.Series(elevation, index=times, name="solar_elevation_deg")


def is_daylight(lat: float, lon: float, times: pd.DatetimeIndex) -> pd.Series:
    """Boolean series marking times when the sun is above the horizon."""
    daylight = solar_elevation_deg(lat, lon, times) > _HORIZON_DEG
    return daylight.rename("is_daylight")


def night_intervals(
    lat: float,
    lon: float,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Dusk-to-dawn intervals covering [start, end], on a 5-minute grid.

    Timestamps must be tz-aware; returned bounds carry the same timezone and
    extend one day past the requested range so chart bands never end mid-night.
    """
    grid = pd.date_range(
        start.floor("h") - pd.Timedelta(days=1),
        end.ceil("h") + pd.Timedelta(days=1),
        freq="5min",
        tz=start.tz,
    )
    dark = (solar_elevation_deg(lat, lon, grid) <= _HORIZON_DEG).to_numpy()
    edges = np.flatnonzero(np.diff(dark.astype(int)))
    starts = [grid[0]] if dark[0] else []
    starts += [grid[i + 1] for i in edges if not dark[i]]
    ends = [grid[i + 1] for i in edges if dark[i]]
    if dark[-1]:
        ends.append(grid[-1])
    return list(zip(starts, ends))
