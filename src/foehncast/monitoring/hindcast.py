"""Hindcast validation — compare past predictions against observed weather.

Reads the prediction event log, fetches observed weather for forecast times
that are now in the past, applies the same labeling function to get
ground-truth quality, and computes accuracy metrics.

Results are persisted to a state file so that Prometheus scrapes can read
cached results without hitting external APIs on every request.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from foehncast.config import get_rider_config, get_spots
from foehncast.feature_pipeline.engineer import engineer_features
from foehncast.feature_pipeline.ingest import fetch_archive
from foehncast.monitoring.prediction_log import read_prediction_history
from foehncast.paths import project_root
from foehncast.training_pipeline.label import compute_quality_index

logger = logging.getLogger(__name__)

# Open-Meteo archive has ~5-day latency for observed data.
_ARCHIVE_BUFFER_HOURS = 120

_EMPTY_RESULT: dict[str, Any] = {
    "validated_count": 0,
    "accuracy": None,
    "mae": None,
    "class_counts": {},
    "validated_at": None,
}


def hindcast_state_path() -> Path:
    """Path to the persisted hindcast validation result."""
    return project_root() / ".state" / "monitoring" / "hindcast-validation.json"


def read_hindcast_result(path: Path | None = None) -> dict[str, Any]:
    """Read the cached hindcast result from the state file."""
    resolved = hindcast_state_path() if path is None else path
    if not resolved.exists():
        return dict(_EMPTY_RESULT)
    try:
        return json.loads(resolved.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        logger.warning("Corrupt hindcast state file at %s", resolved)
        return dict(_EMPTY_RESULT)


def _write_hindcast_result(result: dict[str, Any], path: Path | None = None) -> Path:
    """Persist hindcast validation result to the state file."""
    resolved = hindcast_state_path() if path is None else path
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return resolved


def _spot_lookup() -> dict[str, dict[str, Any]]:
    return {spot["id"]: spot for spot in get_spots()}


def _eligible_predictions(
    history: pd.DataFrame,
    *,
    buffer_hours: int = _ARCHIVE_BUFFER_HOURS,
) -> pd.DataFrame:
    """Filter predictions whose forecast_time is far enough in the past."""
    if history.empty:
        return history

    forecast_times = pd.to_datetime(history["forecast_time"], utc=True)
    cutoff = datetime.now(tz=UTC) - timedelta(hours=buffer_hours)
    mask = forecast_times < cutoff
    eligible = history.loc[mask].copy()
    eligible["forecast_time"] = forecast_times[mask]
    return eligible


def _fetch_observed_features(
    spot: dict[str, Any],
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """Fetch archive weather and engineer features for a spot."""
    raw = fetch_archive(spot["lat"], spot["lon"], start_date, end_date)
    if raw.empty:
        return raw
    engineered = engineer_features(raw, spot["shore_orientation_deg"])
    engineered["spot_id"] = spot["id"]
    return engineered


def run_hindcast_validation(
    *,
    buffer_hours: int = _ARCHIVE_BUFFER_HOURS,
) -> dict[str, Any]:
    """Compare past predictions against observed weather outcomes.

    Returns a summary dict with accuracy, MAE, and per-class counts.
    """
    history = read_prediction_history()
    eligible = _eligible_predictions(history, buffer_hours=buffer_hours)

    if eligible.empty:
        logger.info("No eligible predictions for hindcast validation")
        result = dict(_EMPTY_RESULT, validated_at=datetime.now(tz=UTC).isoformat())
        _write_hindcast_result(result)
        return result

    spots = _spot_lookup()
    rider_config = get_rider_config()

    # Group by spot and fetch observed weather per date range.
    observed_frames: list[pd.DataFrame] = []
    for spot_id, group in eligible.groupby("spot_id"):
        spot = spots.get(str(spot_id))
        if spot is None:
            logger.warning("Unknown spot_id in prediction log: %s", spot_id)
            continue

        forecast_times = group["forecast_time"]
        start_date = forecast_times.min().strftime("%Y-%m-%d")
        end_date = forecast_times.max().strftime("%Y-%m-%d")

        try:
            features = _fetch_observed_features(spot, start_date, end_date)
        except Exception:
            logger.exception(
                "Failed to fetch archive data for %s (%s to %s)",
                spot_id,
                start_date,
                end_date,
            )
            continue

        if features.empty:
            continue

        # Compute ground-truth quality from observed weather.
        truth = compute_quality_index(features, rider_config)
        features["actual_quality_index"] = truth
        observed_frames.append(features)

    if not observed_frames:
        logger.info("No observed data retrieved for hindcast validation")
        result = dict(_EMPTY_RESULT, validated_at=datetime.now(tz=UTC).isoformat())
        _write_hindcast_result(result)
        return result

    observed = pd.concat(observed_frames)

    # Round forecast_time to nearest hour for joining.
    eligible = eligible.copy()
    eligible["forecast_hour"] = eligible["forecast_time"].dt.round("h")

    # Build join key from observed data.
    observed = observed.copy()
    observed_time = (
        observed.index.tz_convert(UTC)
        if observed.index.tz
        else observed.index.tz_localize(UTC)
    )
    observed["forecast_hour"] = observed_time.round("h")

    # Join predictions to observed ground truth.
    merged = eligible.merge(
        observed[["spot_id", "forecast_hour", "actual_quality_index"]],
        on=["spot_id", "forecast_hour"],
        how="inner",
    )

    if merged.empty:
        logger.info("No prediction/observation pairs matched after join")
        result = dict(_EMPTY_RESULT, validated_at=datetime.now(tz=UTC).isoformat())
        _write_hindcast_result(result)
        return result

    # Compute metrics.
    predicted = merged["quality_index"].astype(float)
    actual = merged["actual_quality_index"].astype(float)

    predicted_class = predicted.round().astype(int)
    actual_class = actual.round().astype(int)

    accuracy = float((predicted_class == actual_class).mean())
    mae = float(np.abs(predicted - actual).mean())
    validated_count = len(merged)

    class_counts = merged.groupby(actual_class.rename("quality_class")).size().to_dict()

    result = {
        "validated_count": validated_count,
        "accuracy": accuracy,
        "mae": mae,
        "class_counts": {str(k): int(v) for k, v in class_counts.items()},
        "validated_at": datetime.now(tz=UTC).isoformat(),
    }
    _write_hindcast_result(result)
    logger.info(
        "Hindcast validation: %d pairs, accuracy=%.3f, MAE=%.3f",
        validated_count,
        accuracy,
        mae,
    )
    return result
