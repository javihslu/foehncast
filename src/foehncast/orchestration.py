"""High-level orchestration helpers for local Airflow DAGs."""

from __future__ import annotations

import os
from pathlib import Path

import mlflow
import pandas as pd

from foehncast.config import get_mlflow_config, get_spots
from foehncast.feature_pipeline.engineer import engineer_features
from foehncast.feature_pipeline.ingest import fetch_all_spots
from foehncast.feature_pipeline.store import write_features
from foehncast.feature_pipeline.validate import run_validation
from foehncast.training_pipeline.evaluate import generate_evaluation_report
from foehncast.training_pipeline.register import promote_model, register_model

_ROOT = Path(__file__).resolve().parent.parent.parent


def _tracking_uri() -> str:
    mlflow_config = get_mlflow_config()
    return os.getenv("MLFLOW_TRACKING_URI", mlflow_config["tracking_uri"])


def run_feature_pipeline(dataset: str = "train") -> list[str]:
    """Fetch, engineer, validate, and store features for all configured spots."""
    forecasts_by_spot = fetch_all_spots()
    stored_spots: list[str] = []

    for spot in get_spots():
        spot_id = spot["id"]
        forecast_df = forecasts_by_spot.get(spot_id, pd.DataFrame())
        if forecast_df.empty:
            continue

        feature_df = engineer_features(forecast_df, spot["shore_orientation_deg"])
        validation = run_validation(feature_df, spot_id)
        if not validation.is_valid:
            raise ValueError(f"Feature validation failed for spot '{spot_id}'")

        write_features(feature_df, spot_id=spot_id, dataset=dataset)
        stored_spots.append(spot_id)

    if not stored_spots:
        raise ValueError("No feature data was generated for any configured spot")

    return stored_spots


def evaluate_training_run(training_run_id: str, dataset: str = "train") -> str:
    """Resume a training run, log evaluation metrics, and return the report path."""
    mlflow.set_tracking_uri(_tracking_uri())
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
