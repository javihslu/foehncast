"""Register and load models from the MLflow registry."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import mlflow

from foehncast.config import get_mlflow_config, get_mlflow_tracking_uri

if TYPE_CHECKING:
    from mlflow.entities.model_registry import ModelVersion


def _resolved_model_name(model_name: str | None, mlflow_config: dict[str, Any]) -> str:
    return model_name or mlflow_config["model_name"]


def _registry_alias(stage: str, mlflow_config: dict[str, Any]) -> str:
    normalized_stage = stage.strip().lower()
    if normalized_stage == "production":
        return mlflow_config.get("champion_alias", "champion")

    return normalized_stage


def register_model(run_id: str, model_name: str | None = None) -> "ModelVersion":
    """Register the trained model artifact from a run and return its version."""
    mlflow_config = get_mlflow_config()
    resolved_model_name = _resolved_model_name(model_name, mlflow_config)
    mlflow.set_tracking_uri(get_mlflow_tracking_uri())
    return mlflow.register_model(f"runs:/{run_id}/model", resolved_model_name)


def promote_model(
    model_name: str | None, version: str | int, stage: str = "Production"
) -> None:
    """Promote a registered model version by assigning the configured alias."""
    mlflow_config = get_mlflow_config()
    resolved_model_name = _resolved_model_name(model_name, mlflow_config)
    mlflow.set_tracking_uri(get_mlflow_tracking_uri())

    client = mlflow.MlflowClient()
    client.set_registered_model_alias(
        resolved_model_name,
        _registry_alias(stage, mlflow_config),
        str(version),
    )


def get_production_model(model_name: str | None = None) -> Any:
    """Load the currently deployed production model from the registry."""
    mlflow_config = get_mlflow_config()
    resolved_model_name = _resolved_model_name(model_name, mlflow_config)
    alias = _registry_alias("Production", mlflow_config)
    mlflow.set_tracking_uri(get_mlflow_tracking_uri())
    return mlflow.pyfunc.load_model(f"models:/{resolved_model_name}@{alias}")
