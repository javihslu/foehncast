"""Load workload configuration from config.yaml and resolve runtime bindings explicitly."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

from foehncast.env import env_value
from foehncast.paths import project_root

_config: dict[str, Any] | None = None

_DEFAULT_STORAGE_BACKEND = "s3"
_DEFAULT_STORAGE_S3_BUCKET = "foehncast-data"
_DEFAULT_BIGQUERY_DATASET = "foehncast"
_DEFAULT_BIGQUERY_TABLE = "forecast_features"
_DEFAULT_BIGQUERY_PARTITION_GRANULARITY = "DAY"
_DEFAULT_CURATED_FEATURE_RETENTION_DAYS = 730
_DEFAULT_PREDICTION_EVENT_DATASET = "foehncast_monitoring"
_DEFAULT_PREDICTION_EVENT_TABLE = "prediction_events"
_DEFAULT_PREDICTION_EVENT_RETENTION_DAYS = 180
_DEFAULT_MLFLOW_TRACKING_URI = "http://localhost:5001"


def _resolved_dict_section(name: str) -> dict[str, Any]:
    section = load_config().get(name, {})
    if not isinstance(section, dict):
        return {}
    return copy.deepcopy(section)


def _resolved_string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        candidates = value.split(",")
    elif isinstance(value, (list, tuple)):
        candidates = value
    else:
        candidates = []

    return [str(item).strip() for item in candidates if str(item).strip()]


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(parsed, 1)


def _resolved_warehouse_contract(
    raw_contract: Any,
    *,
    default_dataset: str,
    default_table: str,
    default_partition_field: str,
    default_cluster_fields: tuple[str, ...],
    default_retention_days: int,
) -> dict[str, Any]:
    contract = raw_contract if isinstance(raw_contract, dict) else {}

    cluster_fields = _resolved_string_list(contract.get("cluster_fields"))
    if not cluster_fields:
        cluster_fields = list(default_cluster_fields)

    return {
        "dataset": str(contract.get("dataset", "")).strip() or default_dataset,
        "table": str(contract.get("table", "")).strip() or default_table,
        "partition_field": (
            str(contract.get("partition_field", "")).strip() or default_partition_field
        ),
        "partition_granularity": (
            str(contract.get("partition_granularity", "")).strip().upper()
            or _DEFAULT_BIGQUERY_PARTITION_GRANULARITY
        ),
        "cluster_fields": cluster_fields,
        "retention_days": _positive_int(
            contract.get("retention_days"),
            default_retention_days,
        ),
    }


def _config_path() -> Path:
    configured_path = env_value("FOEHNCAST_CONFIG_PATH")
    if configured_path is not None:
        return Path(configured_path).expanduser()

    return project_root() / "config.yaml"


def load_config(path: Path | None = None) -> dict[str, Any]:
    """Load config.yaml and cache it."""
    global _config
    if _config is None or path is not None:
        p = path or _config_path()
        with open(p) as f:
            _config = yaml.safe_load(f)
    return copy.deepcopy(_config)


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
    """Return storage mode plus runtime-bound storage wiring."""
    storage = _resolved_dict_section("storage")
    warehouse = _resolved_dict_section("warehouse")

    storage["backend"] = (
        env_value("STORAGE_BACKEND")
        or str(storage.get("backend", "")).strip()
        or _DEFAULT_STORAGE_BACKEND
    )
    storage["s3_bucket"] = env_value("STORAGE_S3_BUCKET") or _DEFAULT_STORAGE_S3_BUCKET

    s3_endpoint = env_value("STORAGE_S3_ENDPOINT")
    if s3_endpoint:
        storage["s3_endpoint"] = s3_endpoint
    else:
        storage.pop("s3_endpoint", None)

    bigquery_project_id = env_value(
        "STORAGE_BIGQUERY_PROJECT_ID",
        "GCP_PROJECT_ID",
        "GOOGLE_CLOUD_PROJECT",
    )
    if bigquery_project_id:
        storage["bigquery_project_id"] = bigquery_project_id
    else:
        storage.pop("bigquery_project_id", None)

    storage["bigquery_dataset"] = (
        env_value("STORAGE_BIGQUERY_DATASET") or _DEFAULT_BIGQUERY_DATASET
    )
    storage["bigquery_table"] = (
        env_value("STORAGE_BIGQUERY_TABLE") or _DEFAULT_BIGQUERY_TABLE
    )

    storage["warehouse_contracts"] = {
        "curated_features": _resolved_warehouse_contract(
            warehouse.get("curated_features"),
            default_dataset=storage["bigquery_dataset"],
            default_table=storage["bigquery_table"],
            default_partition_field="forecast_time",
            default_cluster_fields=("dataset_name", "spot_id"),
            default_retention_days=_DEFAULT_CURATED_FEATURE_RETENTION_DAYS,
        ),
        "prediction_events": _resolved_warehouse_contract(
            warehouse.get("prediction_events"),
            default_dataset=_DEFAULT_PREDICTION_EVENT_DATASET,
            default_table=_DEFAULT_PREDICTION_EVENT_TABLE,
            default_partition_field="prediction_timestamp",
            default_cluster_fields=("model_version", "endpoint", "spot_id"),
            default_retention_days=_DEFAULT_PREDICTION_EVENT_RETENTION_DAYS,
        ),
    }

    return storage


def get_validation_config() -> dict[str, Any]:
    """Return the validation settings."""
    return load_config()["validation"]


def get_mlflow_config() -> dict[str, Any]:
    """Return the MLflow settings."""
    return _resolved_dict_section("mlflow")


def get_mlflow_tracking_uri() -> str:
    """Return the resolved MLflow tracking URI."""
    return env_value("MLFLOW_TRACKING_URI") or _DEFAULT_MLFLOW_TRACKING_URI


def get_inference_config() -> dict[str, Any]:
    """Return the inference settings."""
    return load_config()["inference"]


def get_monitoring_config() -> dict[str, Any]:
    """Return the monitoring settings."""
    return load_config()["monitoring"]
