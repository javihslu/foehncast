"""Load and manage configuration from config.yaml."""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

import yaml

_ROOT = Path(__file__).resolve().parent.parent.parent  # foehncast/
_CONFIG_PATH = _ROOT / "config.yaml"
_config: dict[str, Any] | None = None

_ENV_OVERRIDES: dict[tuple[str, str], tuple[str, ...]] = {
    ("storage", "backend"): ("STORAGE_BACKEND",),
    ("storage", "local_path"): ("STORAGE_LOCAL_PATH",),
    ("storage", "s3_bucket"): ("STORAGE_S3_BUCKET",),
    ("storage", "s3_endpoint"): (
        "STORAGE_S3_ENDPOINT",
        "OBJECTSTORE_ENDPOINT",
        "FSSPEC_S3_ENDPOINT_URL",
    ),
    ("storage", "bigquery_project_id"): (
        "STORAGE_BIGQUERY_PROJECT_ID",
        "GCP_PROJECT_ID",
        "GOOGLE_CLOUD_PROJECT",
    ),
    ("storage", "bigquery_dataset"): ("STORAGE_BIGQUERY_DATASET",),
    ("storage", "bigquery_table"): ("STORAGE_BIGQUERY_TABLE",),
    ("gcp", "project_id"): ("GCP_PROJECT_ID", "GOOGLE_CLOUD_PROJECT"),
    ("gcp", "location"): ("GCP_LOCATION",),
    ("gcp", "bucket_name"): ("GCP_BUCKET_NAME",),
    ("gcp", "cloud_run_service"): ("CLOUD_RUN_SERVICE_NAME",),
    ("mlflow", "tracking_uri"): ("MLFLOW_TRACKING_URI",),
}


def _env_value(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value is None:
            continue
        stripped = value.strip()
        if stripped:
            return stripped
    return None


def _apply_env_overrides(config: dict[str, Any]) -> dict[str, Any]:
    resolved = copy.deepcopy(config)

    for (section, key), env_names in _ENV_OVERRIDES.items():
        section_values = resolved.get(section)
        if not isinstance(section_values, dict):
            continue

        override = _env_value(*env_names)
        if override is not None:
            section_values[key] = override

    return resolved


def load_config(path: Path | None = None) -> dict[str, Any]:
    """Load config.yaml and cache it."""
    global _config
    if _config is None or path is not None:
        p = path or _CONFIG_PATH
        with open(p) as f:
            _config = yaml.safe_load(f)
    return _apply_env_overrides(_config)


def get_spots() -> list[dict[str, Any]]:
    """Return the list of spot configurations."""
    return load_config()["spots"]


def get_api_config() -> dict[str, Any]:
    """Return the api section of the config."""
    return load_config()["api"]


def get_rider_config() -> dict[str, Any]:
    """Return the rider profile."""
    return load_config()["rider"]


def get_model_config() -> dict[str, Any]:
    """Return the model training settings."""
    return load_config()["model"]


def get_labeling_config() -> dict[str, Any]:
    """Return the synthetic label settings."""
    return load_config()["labeling"]


def get_storage_config() -> dict[str, Any]:
    """Return the storage settings."""
    return load_config()["storage"]


def get_gcp_config() -> dict[str, Any]:
    """Return the GCP deployment settings."""
    return load_config()["gcp"]


def get_gcp_project_id() -> str | None:
    """Return the resolved GCP project ID."""
    return get_gcp_config().get("project_id")


def get_validation_config() -> dict[str, Any]:
    """Return the validation settings."""
    return load_config()["validation"]


def get_mlflow_config() -> dict[str, Any]:
    """Return the MLflow settings."""
    return load_config()["mlflow"]


def get_mlflow_tracking_uri() -> str:
    """Return the resolved MLflow tracking URI."""
    return get_mlflow_config()["tracking_uri"]


def get_inference_config() -> dict[str, Any]:
    """Return the inference settings."""
    return load_config()["inference"]


def get_monitoring_config() -> dict[str, Any]:
    """Return the monitoring settings."""
    return load_config()["monitoring"]
