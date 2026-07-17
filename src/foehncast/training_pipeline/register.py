"""Register and load models from the MLflow registry."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import mlflow
from mlflow.exceptions import MlflowException

from foehncast.config import (
    configure_mlflow_auth,
    get_mlflow_config,
    get_mlflow_tracking_uri,
)

if TYPE_CHECKING:
    from mlflow.entities.model_registry import ModelVersion


def _resolved_model_name(model_name: str | None, mlflow_config: dict[str, Any]) -> str:
    return model_name or mlflow_config["model_name"]


def _normalized_alias(alias: str, *, label: str = "Model alias") -> str:
    normalized_alias = alias.strip()
    if not normalized_alias:
        raise ValueError(f"{label} must be non-empty")
    return normalized_alias


def _normalized_version(version: str | int) -> str:
    normalized_version = str(version).strip()
    if not normalized_version:
        raise ValueError("Model version must be non-empty")
    return normalized_version


def _configured_mlflow_client(mlflow_module: Any, tracking_uri: str) -> Any:
    mlflow_module.set_tracking_uri(tracking_uri)
    configure_mlflow_auth()
    return mlflow_module.MlflowClient()


def _registry_alias(stage: str, mlflow_config: dict[str, Any]) -> str:
    normalized_stage = stage.strip().lower()
    if normalized_stage == "production":
        return mlflow_config.get("champion_alias", "champion")
    if normalized_stage == "candidate":
        return mlflow_config.get("candidate_alias", "candidate")

    return normalized_stage


def _logged_model_uri_for_run(run_id: str, client: Any) -> str | None:
    if not hasattr(client, "get_run") or not hasattr(client, "search_logged_models"):
        return None

    run = client.get_run(run_id)
    experiment_id = run.info.experiment_id
    logged_models = client.search_logged_models(
        experiment_ids=[experiment_id],
        filter_string=f"source_run_id = '{run_id}'",
        max_results=20,
    )
    if not logged_models:
        return None

    for logged_model in logged_models:
        if getattr(logged_model, "name", None) == "model":
            return logged_model.model_uri

    return logged_models[0].model_uri


def register_model(run_id: str, model_name: str | None = None) -> "ModelVersion":
    """Register the trained model artifact from a run and return its version."""
    mlflow_config = get_mlflow_config()
    resolved_model_name = _resolved_model_name(model_name, mlflow_config)
    client = _configured_mlflow_client(mlflow, get_mlflow_tracking_uri())
    model_uri = _logged_model_uri_for_run(run_id, client) or f"runs:/{run_id}/model"
    return mlflow.register_model(model_uri, resolved_model_name)


def promote_model(
    model_name: str | None, version: str | int, stage: str = "Production"
) -> None:
    """Promote a registered model version by assigning the configured alias."""
    mlflow_config = get_mlflow_config()
    assign_model_alias(
        _registry_alias(stage, mlflow_config),
        version,
        model_name=model_name,
    )


def assign_model_alias(
    alias: str,
    version: str | int,
    model_name: str | None = None,
) -> None:
    """Assign an explicit alias to a registered model version."""
    normalized_alias = _normalized_alias(alias)
    normalized_version = _normalized_version(version)

    mlflow_config = get_mlflow_config()
    resolved_model_name = _resolved_model_name(model_name, mlflow_config)
    client = _configured_mlflow_client(mlflow, get_mlflow_tracking_uri())
    client.set_registered_model_alias(
        resolved_model_name,
        normalized_alias,
        normalized_version,
    )


def ensure_champion_alias(version: str | int, model_name: str | None = None) -> bool:
    """Bootstrap the champion alias onto this version when none exists yet."""
    mlflow_config = get_mlflow_config()
    resolved_model_name = _resolved_model_name(model_name, mlflow_config)
    champion = mlflow_config.get("champion_alias", "champion")
    client = _configured_mlflow_client(mlflow, get_mlflow_tracking_uri())
    try:
        client.get_model_version_by_alias(resolved_model_name, champion)
        return False
    except MlflowException:
        client.set_registered_model_alias(
            resolved_model_name,
            champion,
            _normalized_version(version),
        )
        return True


def get_production_model(model_name: str | None = None) -> Any:
    """Load a registry model by alias, defaulting to the production alias."""
    mlflow_config = get_mlflow_config()
    return get_model_by_alias(
        _registry_alias("Production", mlflow_config),
        model_name=model_name,
    )


def get_model_by_alias(alias: str, model_name: str | None = None) -> Any:
    """Load a registry model from an explicit alias."""
    normalized_alias = _normalized_alias(alias)

    mlflow_config = get_mlflow_config()
    resolved_model_name = _resolved_model_name(model_name, mlflow_config)
    mlflow.set_tracking_uri(get_mlflow_tracking_uri())
    configure_mlflow_auth()
    return mlflow.pyfunc.load_model(f"models:/{resolved_model_name}@{normalized_alias}")
