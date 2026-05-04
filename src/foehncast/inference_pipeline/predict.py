"""Prediction logic for live spot forecasts."""

from __future__ import annotations

from typing import Any

import mlflow
import pandas as pd

from foehncast.config import (
    get_inference_config,
    get_mlflow_config,
    get_mlflow_tracking_uri,
    get_model_config,
    get_spots,
)
from foehncast.feature_pipeline.engineer import engineer_features
from foehncast.feature_pipeline.ingest import fetch_forecast
from foehncast.training_pipeline.register import get_production_model


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


def get_serving_model_version(model_name: str | None = None) -> str:
    """Return the MLflow registry version currently assigned to the serving alias."""
    mlflow_config = get_mlflow_config()
    resolved_model_name = model_name or mlflow_config["model_name"]
    alias = mlflow_config.get("champion_alias", "champion")

    mlflow.set_tracking_uri(get_mlflow_tracking_uri())
    client = mlflow.MlflowClient()
    model_version = client.get_model_version_by_alias(resolved_model_name, alias)
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
    model = get_production_model()
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

        predictions.append(
            {
                "spot_id": spot["id"],
                "spot_name": spot["name"],
                "forecast": forecast_rows,
            }
        )

    return {
        "model_version": get_serving_model_version(),
        "predictions": predictions,
    }
