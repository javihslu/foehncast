"""Synthetic label generation from physics rules."""

from __future__ import annotations

from typing import Any

import pandas as pd

from foehncast.config import get_labeling_config

_REQUIRED_COLUMNS = {
    "wind_speed_10m",
    "wind_gusts_10m",
    "wind_steadiness",
    "gust_factor",
    "shore_alignment",
}


def _require_columns(features_df: pd.DataFrame) -> None:
    missing = sorted(_REQUIRED_COLUMNS - set(features_df.columns))
    if missing:
        raise KeyError(f"Missing required columns for labeling: {', '.join(missing)}")


def _minimum_rideable_wind(
    labeling_cfg: dict[str, Any], rider_config: dict[str, Any]
) -> float:
    minimum_cfg = labeling_cfg["minimum_wind_speed_10m"]
    if rider_config["weight_kg"] <= minimum_cfg["light_rider_max_weight_kg"]:
        return float(minimum_cfg["light_rider_min_kts"])
    return float(minimum_cfg["default_min_kts"])


def _is_perfect_storm(row: pd.Series, perfect_cfg: dict[str, Any]) -> bool:
    return (
        perfect_cfg["min_kts"] <= row["wind_speed_10m"] <= perfect_cfg["max_kts"]
        and row["gust_factor"] <= perfect_cfg["max_gust_factor"]
        and row["shore_alignment"] >= perfect_cfg["min_shore_alignment"]
        and row["wind_steadiness"] <= perfect_cfg["max_wind_steadiness"]
    )


def _base_quality(
    wind_speed_10m: float, minimum_wind: float, bands_cfg: dict[str, Any]
) -> int:
    if wind_speed_10m < minimum_wind:
        return 1
    if wind_speed_10m < bands_cfg["marginal"]["max_kts"]:
        return 2
    if wind_speed_10m < bands_cfg["good_enough"]["max_kts"]:
        return 3
    if wind_speed_10m <= bands_cfg["fun_day"]["max_kts"]:
        return 4
    return 3


def _score_row(
    row: pd.Series, labeling_cfg: dict[str, Any], minimum_wind: float
) -> int:
    dangerous_cfg = labeling_cfg["dangerous"]
    if (
        row["wind_speed_10m"] > dangerous_cfg["max_wind_speed_10m_kts"]
        or row["wind_gusts_10m"] > dangerous_cfg["max_wind_gusts_10m_kts"]
    ):
        return 0

    if _is_perfect_storm(row, labeling_cfg["bands"]["perfect_storm"]):
        return 5

    return _base_quality(row["wind_speed_10m"], minimum_wind, labeling_cfg["bands"])


def compute_quality_index(
    features_df: pd.DataFrame, rider_config: dict[str, Any]
) -> pd.Series:
    """Compute a synthetic 0-5 quality index for each forecast row."""
    _require_columns(features_df)

    labeling_cfg = get_labeling_config()
    minimum_wind = _minimum_rideable_wind(labeling_cfg, rider_config)
    quality = features_df.apply(_score_row, axis=1, args=(labeling_cfg, minimum_wind))
    return quality.astype("int64").rename("quality_index")


def label_dataset(
    features_df: pd.DataFrame, rider_config: dict[str, Any]
) -> pd.DataFrame:
    """Return a labeled copy of the feature dataframe."""
    labeled = features_df.copy()
    labeled["quality_index"] = compute_quality_index(labeled, rider_config)
    return labeled
