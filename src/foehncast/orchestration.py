"""High-level orchestration helpers for Airflow-managed ML jobs."""

from __future__ import annotations

import logging
import os

import mlflow
import pandas as pd

from foehncast.config import (
    get_mlflow_config,
    get_mlflow_tracking_uri,
    get_spots,
    get_storage_config,
)
from foehncast.feature_pipeline.engineer import engineer_features
from foehncast.feature_pipeline.ingest import fetch_all_spots
from foehncast.feature_pipeline.store import read_features, write_features
from foehncast.feature_pipeline.validate import run_validation
from foehncast.monitoring.drift import detect_data_drift, push_drift_metrics
from foehncast.monitoring.pipeline_metrics import (
    build_feature_pipeline_run_summary,
    build_feature_pipeline_spot_summary,
    emit_feature_pipeline_run_summary,
)
from foehncast.paths import project_root
from foehncast.training_pipeline.evaluate import generate_evaluation_report
from foehncast.training_pipeline.register import promote_model, register_model

logger = logging.getLogger(__name__)


def _read_optional_feature_slice(spot_id: str, dataset: str) -> pd.DataFrame:
    try:
        return read_features(spot_id=spot_id, dataset=dataset)
    except FileNotFoundError:
        return pd.DataFrame()
    except Exception:
        logger.exception(
            "Failed to load prior stored features for drift monitoring on spot '%s'",
            spot_id,
        )
        return pd.DataFrame()


def _feature_drift_frame(
    frame: pd.DataFrame,
    *,
    spot_id: str,
    dataset: str,
) -> pd.DataFrame:
    tagged = frame.copy()
    tagged.attrs = {
        **getattr(tagged, "attrs", {}),
        "dataset_name": spot_id,
        "dataset_version": dataset,
    }
    return tagged


def _emit_feature_drift_metrics(
    *,
    spot_id: str,
    dataset: str,
    reference_df: pd.DataFrame,
    current_df: pd.DataFrame,
) -> bool:
    if reference_df.empty or current_df.empty:
        return False

    try:
        report = detect_data_drift(
            _feature_drift_frame(reference_df, spot_id=spot_id, dataset=dataset),
            _feature_drift_frame(current_df, spot_id=spot_id, dataset=dataset),
        )
        push_drift_metrics(report)
        return report.dataset_drift
    except Exception:
        logger.exception(
            "Failed to emit feature drift metrics for spot '%s' in dataset '%s'",
            spot_id,
            dataset,
        )
        return False


def resolve_airflow_schedule(
    schedule: str | None, *, default: str | None = None
) -> str | None:
    """Normalize an Airflow schedule string, allowing explicit opt-out values."""
    candidate = default if schedule is None else schedule
    if candidate is None:
        return None

    normalized = candidate.strip()
    if not normalized:
        return None

    if normalized.lower() in {"none", "off", "false", "manual"}:
        return None

    return normalized


def resolve_auto_retraining_mode(
    mode: str | None, *, default: str | None = "always"
) -> str | None:
    """Normalize Airflow auto-retraining mode values."""
    candidate = default if mode is None else mode
    if candidate is None:
        return None

    normalized = candidate.strip().lower()
    if not normalized or normalized in {"none", "off", "false", "manual"}:
        return None

    if normalized in {"always", "new-data", "new_data", "on-success", "on_success"}:
        return "always"

    if normalized in {"drift", "drift-only", "drift_only"}:
        return "drift"

    raise ValueError(
        "Unsupported auto retraining mode. Use 'always', 'drift', or 'off'."
    )


def should_auto_retrain(
    feature_result: dict[str, object], mode: str | None = "always"
) -> bool:
    """Return whether the Airflow feature refresh should continue into retraining."""
    resolved_mode = resolve_auto_retraining_mode(mode, default="always")
    if resolved_mode is None:
        return False

    stored_spots = [
        str(spot_id).strip()
        for spot_id in feature_result.get("stored_spots", [])
        if str(spot_id).strip()
    ]
    if resolved_mode == "always":
        return bool(stored_spots)

    return bool(feature_result.get("dataset_drift_detected", False))


def _run_feature_pipeline_result(dataset: str = "train") -> dict[str, object]:
    """Run the feature pipeline and return stored spots plus retraining context."""
    storage_backend = get_storage_config()["backend"]
    spots = get_spots()
    forecasts_by_spot: dict[str, pd.DataFrame] = {}
    stored_spots: list[str] = []
    drifted_spots: list[str] = []
    spot_summaries: list[dict[str, object]] = []
    run_error: str | None = None

    try:
        forecasts_by_spot = fetch_all_spots()

        for spot in spots:
            spot_id = spot["id"]
            forecast_df = forecasts_by_spot.get(spot_id, pd.DataFrame())
            if forecast_df.empty:
                spot_summaries.append(
                    build_feature_pipeline_spot_summary(
                        spot_id=spot_id,
                        forecast_df=forecast_df,
                        status="skipped",
                        error="No forecast data returned for this spot",
                    )
                )
                continue

            feature_df = pd.DataFrame()
            previous_stored_df = _read_optional_feature_slice(spot_id, dataset)
            validation = None
            stored_df = pd.DataFrame()

            try:
                feature_df = engineer_features(
                    forecast_df, spot["shore_orientation_deg"]
                )
                validation = run_validation(feature_df, spot_id)
                if not validation.is_valid:
                    raise ValueError(f"Feature validation failed for spot '{spot_id}'")

                write_features(feature_df, spot_id=spot_id, dataset=dataset)
                stored_df = read_features(spot_id=spot_id, dataset=dataset)
                if _emit_feature_drift_metrics(
                    spot_id=spot_id,
                    dataset=dataset,
                    reference_df=previous_stored_df,
                    current_df=stored_df,
                ):
                    drifted_spots.append(spot_id)
            except Exception as exc:
                spot_summaries.append(
                    build_feature_pipeline_spot_summary(
                        spot_id=spot_id,
                        forecast_df=forecast_df,
                        feature_df=feature_df,
                        validation=validation,
                        stored_df=stored_df,
                        status="failed",
                        error=str(exc),
                    )
                )
                raise

            spot_summaries.append(
                build_feature_pipeline_spot_summary(
                    spot_id=spot_id,
                    forecast_df=forecast_df,
                    feature_df=feature_df,
                    validation=validation,
                    stored_df=stored_df,
                    status="stored",
                )
            )
            stored_spots.append(spot_id)

        if not stored_spots:
            raise ValueError("No feature data was generated for any configured spot")

        return {
            "dataset": dataset,
            "storage_backend": storage_backend,
            "stored_spots": stored_spots,
            "drifted_spots": drifted_spots,
            "dataset_drift_detected": bool(drifted_spots),
        }
    except Exception as exc:
        run_error = str(exc)
        raise
    finally:
        fetched_spots = [
            spot["id"]
            for spot in spots
            if not forecasts_by_spot.get(spot["id"], pd.DataFrame()).empty
        ]
        summary = build_feature_pipeline_run_summary(
            dataset=dataset,
            storage_backend=storage_backend,
            expected_spots=[spot["id"] for spot in spots],
            fetched_spots=fetched_spots,
            stored_spots=stored_spots,
            spot_summaries=spot_summaries,
            run_status="succeeded" if run_error is None else "failed",
            error=run_error,
        )
        try:
            emit_feature_pipeline_run_summary(summary)
        except Exception:
            logger.exception("Failed to emit feature pipeline run summary")


def run_feature_pipeline(dataset: str = "train") -> list[str]:
    """Fetch, engineer, validate, store, and monitor features for all spots."""
    return list(_run_feature_pipeline_result(dataset=dataset)["stored_spots"])


def _scheduled_mlflow_tracking_uri() -> str | None:
    tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "").strip()
    return tracking_uri or None


def run_feature_pipeline_job(dataset: str = "train") -> list[str]:
    """Run the feature pipeline and optionally log a refresh run to MLflow."""
    tracking_uri = _scheduled_mlflow_tracking_uri()
    if tracking_uri is None:
        return run_feature_pipeline(dataset=dataset)

    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(get_mlflow_config()["experiment_name"])

    with mlflow.start_run(run_name=f"feature-{dataset}-refresh"):
        stored_spots = run_feature_pipeline(dataset=dataset)
        mlflow.log_params(
            {
                "dataset": dataset,
                "storage_backend": get_storage_config()["backend"],
                "stored_spots": ",".join(stored_spots),
            }
        )
        mlflow.log_metric("stored_spot_count", len(stored_spots))
        return stored_spots


def run_feature_pipeline_job_context(dataset: str = "train") -> dict[str, object]:
    """Run the feature pipeline and return Airflow-friendly retraining context."""
    result = _run_feature_pipeline_result(dataset=dataset)
    tracking_uri = _scheduled_mlflow_tracking_uri()
    if tracking_uri is None:
        return result

    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(get_mlflow_config()["experiment_name"])

    with mlflow.start_run(run_name=f"feature-{dataset}-refresh"):
        mlflow.log_params(
            {
                "dataset": dataset,
                "storage_backend": result["storage_backend"],
                "stored_spots": ",".join(result["stored_spots"]),
                "drifted_spots": ",".join(result["drifted_spots"]),
            }
        )
        mlflow.log_metric("stored_spot_count", len(result["stored_spots"]))
        mlflow.log_metric("drifted_spot_count", len(result["drifted_spots"]))
        mlflow.log_metric(
            "dataset_drift_detected", float(result["dataset_drift_detected"])
        )
        return result


def evaluate_training_run(training_run_id: str, dataset: str = "train") -> str:
    """Resume a training run, log evaluation metrics, and return the report path."""
    mlflow.set_tracking_uri(get_mlflow_tracking_uri())
    run = mlflow.MlflowClient().get_run(training_run_id)
    metrics = dict(run.data.metrics)
    if not metrics:
        raise ValueError(f"No evaluation metrics found for run '{training_run_id}'")

    report_dir = project_root() / "airflow" / "reports"
    report_path = report_dir / f"evaluation-{training_run_id}.md"

    with mlflow.start_run(run_id=training_run_id):
        return generate_evaluation_report(metrics, str(report_path))


def register_training_run(training_run_id: str, stage: str = "Production") -> str:
    """Register and promote a training run's model, returning the new version."""
    model_version = register_model(training_run_id)
    promote_model(None, model_version.version, stage=stage)
    return str(model_version.version)
