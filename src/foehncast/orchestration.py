"""High-level orchestration helpers for Airflow-managed ML jobs."""

from __future__ import annotations

import logging
import os
from pathlib import Path

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
from foehncast.monitoring.pipeline_metrics import (
    build_feature_pipeline_run_summary,
    build_feature_pipeline_spot_summary,
    emit_feature_pipeline_run_summary,
)
from foehncast.training_pipeline.evaluate import generate_evaluation_report
from foehncast.training_pipeline.register import promote_model, register_model

_ROOT = Path(__file__).resolve().parent.parent.parent
logger = logging.getLogger(__name__)


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


def run_feature_pipeline(dataset: str = "train") -> list[str]:
    """Fetch, engineer, validate, and store features for all configured spots."""
    spots = get_spots()
    forecasts_by_spot: dict[str, pd.DataFrame] = {}
    stored_spots: list[str] = []
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

        return stored_spots
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
            storage_backend=get_storage_config()["backend"],
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


def evaluate_training_run(training_run_id: str, dataset: str = "train") -> str:
    """Resume a training run, log evaluation metrics, and return the report path."""
    mlflow.set_tracking_uri(get_mlflow_tracking_uri())
    run = mlflow.MlflowClient().get_run(training_run_id)
    metrics = dict(run.data.metrics)
    if not metrics:
        raise ValueError(f"No evaluation metrics found for run '{training_run_id}'")

    report_dir = _ROOT / "airflow" / "reports"
    report_path = report_dir / f"evaluation-{training_run_id}.md"

    with mlflow.start_run(run_id=training_run_id):
        return generate_evaluation_report(metrics, str(report_path))


def register_training_run(training_run_id: str, stage: str = "Production") -> str:
    """Register and promote a training run's model, returning the new version."""
    model_version = register_model(training_run_id)
    promote_model(None, model_version.version, stage=stage)
    return str(model_version.version)
