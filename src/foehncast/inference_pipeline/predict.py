"""Prediction logic for live spot forecasts."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import mlflow
import pandas as pd

from foehncast.config import (
    configure_mlflow_auth,
    get_inference_config,
    get_mlflow_config,
    get_mlflow_tracking_uri,
    get_model_config,
    get_spots,
)
from foehncast.env import env_value
from foehncast.feature_pipeline.engineer import engineer_features
from foehncast.feature_pipeline.ingest import fetch_forecast
from foehncast.monitoring.inference_prometheus import observe_model_confidence
from foehncast.training_pipeline.register import get_model_by_alias

logger = logging.getLogger(__name__)

_DEFAULT_SERVING_ALIAS = "champion"

_LATEST_PREDICTIONS_DIR = (
    Path(env_value("FOEHNCAST_STATE_DIR") or ".state") / "predictions"
)
_LATEST_PREDICTIONS_PATH = _LATEST_PREDICTIONS_DIR / "latest.json"
# Maximum age (seconds) before the snapshot is considered stale and live
# inference is triggered instead.  Default: 7 hours (one full pipeline cycle
# plus buffer).
_SNAPSHOT_MAX_AGE_S = int(env_value("FOEHNCAST_PREDICTION_SNAPSHOT_MAX_AGE") or 25200)


def _spot_lookup() -> dict[str, dict[str, Any]]:
    return {spot["id"]: spot for spot in get_spots()}


def _resolve_spots(spot_ids: list[str] | None) -> list[dict[str, Any]]:
    spot_lookup = _spot_lookup()
    if spot_ids is None:
        return list(spot_lookup.values())

    missing_spots = sorted(set(spot_ids) - set(spot_lookup))
    if missing_spots:
        missing = ", ".join(missing_spots)
        raise KeyError(f"Unknown spot requested: {missing}")

    return [spot_lookup[spot_id] for spot_id in spot_ids]


def list_available_spots() -> list[dict[str, Any]]:
    """Return the configured spots available for inference."""
    return [spot.copy() for spot in get_spots()]


def get_serving_model_alias() -> str:
    """Return the registry alias this runtime should serve."""
    override = env_value("FOEHNCAST_MLFLOW_SERVING_ALIAS")
    if override:
        return override

    mlflow_config = get_mlflow_config()
    configured_alias = str(mlflow_config.get("champion_alias", "")).strip()
    return configured_alias or _DEFAULT_SERVING_ALIAS


def get_serving_model_version(
    model_name: str | None = None, alias: str | None = None
) -> str:
    """Return the MLflow registry version currently assigned to the serving alias."""
    mlflow_config = get_mlflow_config()
    resolved_model_name = model_name or mlflow_config["model_name"]
    resolved_alias = alias or get_serving_model_alias()

    mlflow.set_tracking_uri(get_mlflow_tracking_uri())
    configure_mlflow_auth()
    client = mlflow.MlflowClient()
    model_version = client.get_model_version_by_alias(
        resolved_model_name, resolved_alias
    )
    return str(model_version.version)


def _prepare_feature_frame(
    forecast_df: pd.DataFrame, spot: dict[str, Any], feature_columns: list[str]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    engineered_df = engineer_features(forecast_df, spot["shore_orientation_deg"])
    feature_frame = engineered_df[feature_columns].copy().ffill().bfill().fillna(0.0)
    return engineered_df, feature_frame


def predict_spots(spot_ids: list[str] | None = None) -> dict[str, Any]:
    """Fetch forecasts for the requested spots and return model predictions."""
    requested_spots = _resolve_spots(spot_ids)
    serving_alias = get_serving_model_alias()
    model = get_model_by_alias(serving_alias)
    model_config = get_model_config()
    inference_config = get_inference_config()
    feature_columns = model_config["features"]
    max_horizon_hours = inference_config["max_horizon_hours"]
    predictions: list[dict[str, Any]] = []

    for spot in requested_spots:
        forecast_df = fetch_forecast(spot["lat"], spot["lon"])
        forecast_df = forecast_df.head(max_horizon_hours)
        if forecast_df.empty:
            predictions.append(
                {
                    "spot_id": spot["id"],
                    "spot_name": spot["name"],
                    "forecast": [],
                }
            )
            continue

        engineered_df, feature_frame = _prepare_feature_frame(
            forecast_df, spot, feature_columns
        )
        model_predictions = model.predict(feature_frame)
        forecast_rows = []

        for timestamp, quality_index in zip(
            engineered_df.index, model_predictions, strict=False
        ):
            forecast_rows.append(
                {
                    "time": timestamp.isoformat(),
                    "quality_index": float(quality_index),
                }
            )

        if forecast_rows:
            mean_quality = sum(row["quality_index"] for row in forecast_rows) / len(
                forecast_rows
            )
            observe_model_confidence(spot["id"], mean_quality)

        predictions.append(
            {
                "spot_id": spot["id"],
                "spot_name": spot["name"],
                "forecast": forecast_rows,
            }
        )

    return {
        "model_version": get_serving_model_version(alias=serving_alias),
        "predictions": predictions,
    }


# ---------------------------------------------------------------------------
# Prediction snapshot: pre-computed predictions persisted to disk so the UI
# can serve them instantly without re-running inference on every page load.
# ---------------------------------------------------------------------------


def write_latest_predictions(payload: dict[str, Any]) -> Path:
    """Persist the prediction payload as the latest snapshot.

    Called by the inference pipeline orchestrator after a successful run.
    The snapshot is timestamped so consumers can evaluate freshness.
    """
    _LATEST_PREDICTIONS_DIR.mkdir(parents=True, exist_ok=True)
    snapshot = {
        "written_at": time.time(),
        "written_iso": pd.Timestamp.now(tz="UTC").isoformat(),
        **payload,
    }
    _LATEST_PREDICTIONS_PATH.write_text(
        json.dumps(snapshot, default=str), encoding="utf-8"
    )
    logger.info("Wrote prediction snapshot to %s", _LATEST_PREDICTIONS_PATH)
    return _LATEST_PREDICTIONS_PATH


def read_latest_predictions(
    max_age_s: int | None = None,
) -> dict[str, Any] | None:
    """Read the latest prediction snapshot if it exists and is fresh.

    Returns the prediction payload dict (same shape as ``predict_spots``
    output) or *None* if the file is missing, corrupt, or older than
    *max_age_s* seconds.
    """
    age_limit = max_age_s if max_age_s is not None else _SNAPSHOT_MAX_AGE_S
    if not _LATEST_PREDICTIONS_PATH.is_file():
        return None
    try:
        raw = _LATEST_PREDICTIONS_PATH.read_text(encoding="utf-8")
        snapshot = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        logger.warning("Could not read prediction snapshot; falling back to live.")
        return None

    written_at = snapshot.get("written_at")
    if written_at is None:
        return None
    age = time.time() - float(written_at)
    if age > age_limit:
        logger.info(
            "Prediction snapshot is %.0f s old (limit %d s); treating as stale.",
            age,
            age_limit,
        )
        return None

    # Return only the prediction payload fields (strip snapshot metadata).
    return {
        "model_version": snapshot.get("model_version", "unknown"),
        "predictions": snapshot.get("predictions", []),
    }


# ---------------------------------------------------------------------------
# Full inference run: predict + snapshot + monitoring.
# Single entry point used by Airflow, Cloud Run Jobs, and the serve API.
# ---------------------------------------------------------------------------


def run_inference(
    *,
    spot_ids: list[str] | None = None,
    endpoint: str = "scheduled",
) -> dict[str, Any]:
    """Run inference, persist the snapshot, and emit monitoring metrics.

    This is the canonical "do everything" function. Both the Airflow
    orchestrator and the serving API delegate here so the pipeline logic
    lives in one place.
    """
    from foehncast.monitoring.prediction_log import emit_prediction_drift_metrics

    logger.info(
        "Inference run (%s): predicting for %s", endpoint, spot_ids or "all spots"
    )
    prediction_payload = predict_spots(spot_ids=spot_ids)

    n_spots = len(prediction_payload.get("predictions", []))
    model_version = prediction_payload.get("model_version", "unknown")
    logger.info(
        "Inference run (%s): %d spots predicted with model v%s",
        endpoint,
        n_spots,
        model_version,
    )

    # Persist snapshot for fast UI reads (only when all spots were predicted).
    if spot_ids is None:
        write_latest_predictions(prediction_payload)

    emit_prediction_drift_metrics(prediction_payload, endpoint=endpoint)
    logger.info(
        "Inference run (%s): prediction log and drift metrics updated", endpoint
    )
    return prediction_payload
