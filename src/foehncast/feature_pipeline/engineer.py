"""Compute derived forecast features for the model."""

from __future__ import annotations

import numpy as np
import pandas as pd


def _timestamp_index(df: pd.DataFrame) -> pd.DatetimeIndex:
    if isinstance(df.index, pd.DatetimeIndex):
        return df.index
    if "time" in df.columns:
        return pd.DatetimeIndex(pd.to_datetime(df["time"]))
    raise KeyError("Feature engineering requires a DatetimeIndex or 'time' column")


def hour_of_day_sin(df: pd.DataFrame) -> pd.Series:
    """Cyclical encoding of the forecast hour."""
    timestamps = _timestamp_index(df)
    hour_of_day = (
        timestamps.hour + timestamps.minute / 60.0 + timestamps.second / 3600.0
    )
    values = np.sin(2 * np.pi * hour_of_day / 24.0)
    return pd.Series(values, index=df.index, name="hour_of_day_sin")


def hour_of_day_cos(df: pd.DataFrame) -> pd.Series:
    """Cyclical encoding of the forecast hour."""
    timestamps = _timestamp_index(df)
    hour_of_day = (
        timestamps.hour + timestamps.minute / 60.0 + timestamps.second / 3600.0
    )
    values = np.cos(2 * np.pi * hour_of_day / 24.0)
    return pd.Series(values, index=df.index, name="hour_of_day_cos")


def day_of_year_sin(df: pd.DataFrame) -> pd.Series:
    """Cyclical encoding of the day of year."""
    timestamps = _timestamp_index(df)
    day_of_year = timestamps.dayofyear - 1
    days_in_year = np.where(timestamps.is_leap_year, 366.0, 365.0)
    values = np.sin(2 * np.pi * day_of_year / days_in_year)
    return pd.Series(values, index=df.index, name="day_of_year_sin")


def day_of_year_cos(df: pd.DataFrame) -> pd.Series:
    """Cyclical encoding of the day of year."""
    timestamps = _timestamp_index(df)
    day_of_year = timestamps.dayofyear - 1
    days_in_year = np.where(timestamps.is_leap_year, 366.0, 365.0)
    values = np.cos(2 * np.pi * day_of_year / days_in_year)
    return pd.Series(values, index=df.index, name="day_of_year_cos")


def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add simple cyclical time features from each forecast timestamp."""
    out = df.copy()
    out["hour_of_day_sin"] = hour_of_day_sin(df)
    out["hour_of_day_cos"] = hour_of_day_cos(df)
    out["day_of_year_sin"] = day_of_year_sin(df)
    out["day_of_year_cos"] = day_of_year_cos(df)
    return out


def wind_steadiness(df: pd.DataFrame, window: int = 3) -> pd.Series:
    """Coefficient of variation of 10m wind over a rolling window.

    Low values indicate consistent, kiteable conditions.

    Args:
        df: DataFrame with ``wind_speed_10m`` column (hourly).
        window: Rolling window size in hours.

    Returns:
        Series of CV values (std / mean). NaN where mean is zero.
    """
    rolling_mean = df["wind_speed_10m"].rolling(window, min_periods=1).mean()
    rolling_std = df["wind_speed_10m"].rolling(window, min_periods=1).std(ddof=0)
    return (rolling_std / rolling_mean).replace([np.inf, -np.inf], np.nan)


def gust_factor(df: pd.DataFrame) -> pd.Series:
    """Ratio of gust speed to sustained wind.

    High values indicate dangerous, gusty conditions.

    Args:
        df: DataFrame with ``wind_gusts_10m`` and ``wind_speed_10m``.

    Returns:
        Series of gust-to-sustained ratios. NaN where sustained is zero.
    """
    return (df["wind_gusts_10m"] / df["wind_speed_10m"]).replace(
        [np.inf, -np.inf], np.nan
    )


def shore_alignment(df: pd.DataFrame, shore_orientation_deg: float) -> pd.Series:
    """Cosine similarity of wind direction to ideal shore orientation.

    Cross-shore flow (perpendicular) scores highest (1.0).
    Direct onshore/offshore scores lowest (-1.0).

    Args:
        df: DataFrame with ``wind_direction_10m`` column (degrees).
        shore_orientation_deg: Shore normal direction in degrees.

    Returns:
        Series of cosine similarity values in [-1, 1].
    """
    angle_diff = np.radians(df["wind_direction_10m"] - shore_orientation_deg)
    return np.cos(angle_diff)


def engineer_features(df: pd.DataFrame, shore_orientation_deg: float) -> pd.DataFrame:
    """Add all engineered features to a spot forecast DataFrame.

    Args:
        df: Raw forecast DataFrame from ingest (must have
            ``wind_speed_10m``, ``wind_gusts_10m``, ``wind_direction_10m``).
        shore_orientation_deg: Shore orientation for the spot.

    Returns:
        DataFrame with added columns for cyclical time, wind steadiness,
        gust factor, and shore alignment.
    """
    out = add_time_features(df)
    out["wind_steadiness"] = wind_steadiness(df)
    out["gust_factor"] = gust_factor(df)
    out["shore_alignment"] = shore_alignment(df, shore_orientation_deg)
    return out
