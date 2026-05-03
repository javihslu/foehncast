"""Compute derived features (wind scores, gust ratios, consistency metrics)."""

from __future__ import annotations

import numpy as np
import pandas as pd


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
        DataFrame with added columns: ``wind_steadiness``,
        ``gust_factor``, ``shore_alignment``.
    """
    out = df.copy()
    out["wind_steadiness"] = wind_steadiness(df)
    out["gust_factor"] = gust_factor(df)
    out["shore_alignment"] = shore_alignment(df, shore_orientation_deg)
    return out
