"""Prediction logic for live spot forecasts."""

from __future__ import annotations

import json
import logging
import socket
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import mlflow
import pandas as pd
from mlflow.exceptions import MlflowException

from foehncast.config import (
    configure_mlflow_auth,
    get_inference_config,
    get_mlflow_config,
    get_mlflow_tracking_uri,
    get_model_config,
    get_spots,
    get_storage_config,
)
from foehncast.env import env_value
from foehncast.feature_pipeline.engineer import engineer_features, impute_model_features
from foehncast.feature_pipeline.ingest import fetch_forecast
from foehncast.feature_pipeline.store import _s3_endpoint
from foehncast.monitoring.inference_prometheus import observe_mean_predicted_quality
from foehncast.training_pipeline.register import get_model_by_alias

logger = logging.getLogger(__name__)

_DEFAULT_SERVING_ALIAS = "champion"
_DEFAULT_CANDIDATE_ALIAS = "candidate"

_STATE_DIR = env_value("FOEHNCAST_STATE_DIR") or ".state"
_SNAPSHOT_LOCATION = f"{_STATE_DIR.rstrip('/')}/predictions/latest.json"
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


def get_candidate_model_alias() -> str:
    """Return the registry alias for the shadow candidate model."""
    mlflow_config = get_mlflow_config()
    configured_alias = str(mlflow_config.get("candidate_alias", "")).strip()
    return configured_alias or _DEFAULT_CANDIDATE_ALIAS


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
    feature_frame = impute_model_features(engineered_df[feature_columns].copy())
    return engineered_df, feature_frame


def _compute_shadow_divergence(
    scored_frames: list[tuple[pd.DataFrame, Any]],
    serving_version: str,
) -> dict[str, Any] | None:
    """Score the same feature frames with the candidate model and summarise
    how far its predictions diverge from the champion.

    Returns *None* (and never raises) when there is no distinct candidate to
    compare against, or when anything in the shadow path fails. The champion
    run must never fail or change because of shadow scoring.
    """
    if not scored_frames:
        return None
    try:
        candidate_alias = get_candidate_model_alias()
        try:
            candidate_version = get_serving_model_version(alias=candidate_alias)
        except MlflowException:
            return None  # no candidate registered yet
        if candidate_version == serving_version:
            return None  # candidate is the current champion; nothing to compare

        candidate_model = get_model_by_alias(candidate_alias)
        abs_diffs: list[float] = []
        for feature_frame, champion_preds in scored_frames:
            candidate_preds = candidate_model.predict(feature_frame)
            for champion_value, candidate_value in zip(
                champion_preds, candidate_preds, strict=False
            ):
                abs_diffs.append(abs(float(candidate_value) - float(champion_value)))

        if not abs_diffs:
            return None
        return {
            "champion_version": serving_version,
            "candidate_version": candidate_version,
            "mean_abs_divergence": sum(abs_diffs) / len(abs_diffs),
            "max_abs_divergence": max(abs_diffs),
            "compared_rows": len(abs_diffs),
        }
    except Exception:
        logger.warning(
            "Shadow scoring failed; serving the champion without a shadow section.",
            exc_info=True,
        )
        return None


def _artifact_store_reachable(timeout: float = 2.0) -> bool:
    """Return whether the configured S3 artifact store endpoint accepts a TCP connection."""
    endpoint = _s3_endpoint(get_storage_config())
    if not endpoint:
        return True
    parsed = urlparse(endpoint)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        socket.create_connection((parsed.hostname, port), timeout=timeout).close()
    except OSError:
        return False
    return True


def predict_spots(spot_ids: list[str] | None = None) -> dict[str, Any]:
    """Fetch forecasts for the requested spots and return model predictions."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    requested_spots = _resolve_spots(spot_ids)
    serving_alias = get_serving_model_alias()
    if not _artifact_store_reachable():
        endpoint = _s3_endpoint(get_storage_config())
        raise RuntimeError(f"artifact store unreachable at {endpoint}")
    model = get_model_by_alias(serving_alias)
    # Resolve the served version right after loading the model so the reported
    # version matches the weights actually loaded (a later lookup could read a
    # freshly reassigned alias).
    serving_version = get_serving_model_version(alias=serving_alias)
    model_config = get_model_config()
    inference_config = get_inference_config()
    feature_columns = model_config["features"]
    max_horizon_hours = inference_config["max_horizon_hours"]

    # Fetch all forecasts in parallel (I/O-bound Open-Meteo HTTP calls).
    forecast_map: dict[str, pd.DataFrame] = {}
    with ThreadPoolExecutor(max_workers=min(len(requested_spots), 8)) as pool:
        futures = {
            pool.submit(
                fetch_forecast,
                spot["lat"],
                spot["lon"],
                forecast_hours=max_horizon_hours,
            ): spot["id"]
            for spot in requested_spots
        }
        for future in as_completed(futures):
            spot_id = futures[future]
            try:
                forecast_map[spot_id] = future.result().head(max_horizon_hours)
            except Exception:
                logger.warning(
                    "Failed to fetch forecast for %s", spot_id, exc_info=True
                )
                forecast_map[spot_id] = pd.DataFrame()

    # Run model prediction sequentially (CPU-bound, fast).
    predictions: list[dict[str, Any]] = []
    scored_frames: list[tuple[pd.DataFrame, Any]] = []
    for spot in requested_spots:
        forecast_df = forecast_map.get(spot["id"], pd.DataFrame())
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
        scored_frames.append((feature_frame, model_predictions))
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
            observe_mean_predicted_quality(spot["id"], mean_quality)

        predictions.append(
            {
                "spot_id": spot["id"],
                "spot_name": spot["name"],
                "forecast": forecast_rows,
            }
        )

    prediction_payload: dict[str, Any] = {
        "model_version": serving_version,
        "predictions": predictions,
    }

    # Shadow scoring rides along only on full batches (the payload that gets
    # snapshotted and surfaced), reusing the feature frames already prepared
    # for the champion. Subset requests stay byte-identical and skip the
    # candidate model load.
    if spot_ids is None:
        shadow = _compute_shadow_divergence(scored_frames, serving_version)
        if shadow is not None:
            prediction_payload["shadow"] = shadow

    return prediction_payload


# Prediction snapshot: stored predictions (local or GCS) so the UI does
# not re-run inference on every page load.


def _is_gcs_snapshot() -> bool:
    return _SNAPSHOT_LOCATION.startswith("gs://")


def write_latest_predictions(payload: dict[str, Any]) -> str:
    """Persist the prediction payload as the latest snapshot.

    Called by the inference pipeline orchestrator after a successful run.
    The snapshot is timestamped so consumers can evaluate freshness.
    Works with both local filesystem and GCS (when FOEHNCAST_STATE_DIR
    starts with gs://).
    """
    snapshot = {
        "written_at": time.time(),
        "written_iso": pd.Timestamp.now(tz="UTC").isoformat(),
        **payload,
    }

    if _is_gcs_snapshot():
        from foehncast._report_store import write_json_object

        write_json_object(_SNAPSHOT_LOCATION, snapshot)
    else:
        path = Path(_SNAPSHOT_LOCATION)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(snapshot, default=str), encoding="utf-8")

    logger.info("Wrote prediction snapshot to %s", _SNAPSHOT_LOCATION)
    return _SNAPSHOT_LOCATION


def read_latest_predictions(
    max_age_s: int | None = None,
) -> dict[str, Any] | None:
    """Read the latest prediction snapshot if it exists and is fresh.

    Returns the prediction payload dict (same shape as ``predict_spots``
    output) or *None* if the file is missing, corrupt, or older than
    *max_age_s* seconds.  Supports both local and GCS paths.
    """
    age_limit = max_age_s if max_age_s is not None else _SNAPSHOT_MAX_AGE_S

    try:
        if _is_gcs_snapshot():
            from foehncast._report_store import _new_storage_client, _parse_gcs_location

            bucket_name, object_name = _parse_gcs_location(_SNAPSHOT_LOCATION)
            blob = _new_storage_client().bucket(bucket_name).blob(object_name)
            if not blob.exists():
                return None
            raw = blob.download_as_text(encoding="utf-8")
        else:
            path = Path(_SNAPSHOT_LOCATION)
            if not path.is_file():
                return None
            raw = path.read_text(encoding="utf-8")

        snapshot = json.loads(raw)
    except Exception as exc:
        logger.warning(
            "Could not read prediction snapshot (%s); falling back to live.", exc
        )
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
    payload: dict[str, Any] = {
        "model_version": snapshot.get("model_version", "unknown"),
        "predictions": snapshot.get("predictions", []),
    }
    # Carry the optional shadow section through so metrics can render from it.
    shadow = snapshot.get("shadow")
    if shadow is not None:
        payload["shadow"] = shadow
    return payload


# Full inference run used by Airflow, Cloud Run jobs and the serve API.


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
