"""Render the Feast runtime configuration from infrastructure-owned environment."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

import yaml

from foehncast.paths import project_root

_DEFAULT_PROJECT = "foehncast"
_DEFAULT_LOCAL_REGISTRY = "../.state/feast/registry.db"
_DEFAULT_LOCAL_DATASTORE_PROJECT_ID = "foehncast-local"
_DEFAULT_BIGQUERY_DATASET = "foehncast"
_DEFAULT_BIGQUERY_LOCATION = "EU"
_DEFAULT_DATASTORE_DATABASE = "feast-online"


def _env_value(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value is None:
            continue
        stripped = value.strip()
        if stripped:
            return stripped
    return None


def feast_repo_path() -> Path:
    configured_path = _env_value("FOEHNCAST_FEAST_REPO_PATH")
    if configured_path:
        return Path(configured_path).expanduser()
    return project_root() / "feature_repo"


def feast_runtime_config_path(repo_path: Path | None = None) -> Path:
    repo = repo_path or feast_repo_path()
    configured_path = _env_value("FOEHNCAST_FEAST_CONFIG_PATH")
    if configured_path:
        path = Path(configured_path).expanduser()
        if path.is_absolute():
            return path
        return repo.parent / path
    return repo.parent / ".state" / "feast" / "feature_store.runtime.yaml"


def _source_mode() -> str:
    return (_env_value("FOEHNCAST_FEAST_SOURCE") or "local").lower()


def _entity_key_serialization_version() -> int:
    return int(_env_value("FOEHNCAST_FEAST_ENTITY_KEY_SERIALIZATION_VERSION") or "3")


def _base_config() -> dict[str, Any]:
    return {
        "project": _env_value("FOEHNCAST_FEAST_PROJECT") or _DEFAULT_PROJECT,
        "entity_key_serialization_version": _entity_key_serialization_version(),
    }


def _local_datastore_online_store_config() -> dict[str, Any]:
    online_store: dict[str, Any] = {
        "type": "datastore",
        "project_id": _env_value(
            "FOEHNCAST_FEAST_LOCAL_DATASTORE_PROJECT_ID",
            "FOEHNCAST_FEAST_PROJECT_ID",
            "GCP_PROJECT_ID",
            "DATASTORE_PROJECT_ID",
            "GOOGLE_CLOUD_PROJECT",
        )
        or _DEFAULT_LOCAL_DATASTORE_PROJECT_ID,
    }

    namespace = _env_value("FOEHNCAST_FEAST_LOCAL_DATASTORE_NAMESPACE")
    if namespace:
        online_store["namespace"] = namespace

    database = _env_value("FOEHNCAST_FEAST_LOCAL_DATASTORE_DATABASE")
    if database:
        online_store["database"] = database

    return online_store


def _local_runtime_config() -> dict[str, Any]:
    config = _base_config()
    config.update(
        {
            "registry": _env_value("FOEHNCAST_FEAST_REGISTRY")
            or _DEFAULT_LOCAL_REGISTRY,
            "provider": _env_value("FOEHNCAST_FEAST_PROVIDER") or "gcp",
            "offline_store": {"type": "file"},
            "online_store": _local_datastore_online_store_config(),
        }
    )
    return config


def _cloud_runtime_config() -> dict[str, Any]:
    project_id = _env_value(
        "FOEHNCAST_FEAST_PROJECT_ID",
        "GCP_PROJECT_ID",
        "STORAGE_BIGQUERY_PROJECT_ID",
        "GOOGLE_CLOUD_PROJECT",
    )
    if not project_id:
        raise ValueError(
            "Feast BigQuery runtime binding requires GCP_PROJECT_ID or FOEHNCAST_FEAST_PROJECT_ID"
        )

    bucket_name = _env_value("FOEHNCAST_FEAST_GCS_BUCKET", "GCP_BUCKET_NAME")
    registry = _env_value("FOEHNCAST_FEAST_REGISTRY")
    if not registry:
        if not bucket_name:
            raise ValueError(
                "Feast cloud runtime binding requires FOEHNCAST_FEAST_REGISTRY or GCP_BUCKET_NAME"
            )
        registry = f"gs://{bucket_name}/feast/registry.db"

    staging_location = _env_value("FOEHNCAST_FEAST_GCS_STAGING_LOCATION")
    if not staging_location:
        if not bucket_name:
            raise ValueError(
                "Feast cloud runtime binding requires FOEHNCAST_FEAST_GCS_STAGING_LOCATION or GCP_BUCKET_NAME"
            )
        staging_location = f"gs://{bucket_name}/feast/staging"

    online_store: dict[str, Any] = {
        "type": "datastore",
        "project_id": project_id,
        "database": _env_value("FOEHNCAST_FEAST_DATASTORE_DATABASE")
        or _DEFAULT_DATASTORE_DATABASE,
    }
    namespace = _env_value("FOEHNCAST_FEAST_DATASTORE_NAMESPACE")
    if namespace:
        online_store["namespace"] = namespace

    config = _base_config()
    config.update(
        {
            "registry": registry,
            "provider": _env_value("FOEHNCAST_FEAST_PROVIDER") or "gcp",
            "offline_store": {
                "type": "bigquery",
                "project_id": project_id,
                "dataset": _env_value("FOEHNCAST_FEAST_BIGQUERY_DATASET")
                or _DEFAULT_BIGQUERY_DATASET,
                "location": _env_value("FOEHNCAST_FEAST_BIGQUERY_LOCATION")
                or _DEFAULT_BIGQUERY_LOCATION,
                "gcs_staging_location": staging_location,
            },
            "online_store": online_store,
        }
    )
    return config


def resolve_runtime_config() -> dict[str, Any]:
    source_mode = _source_mode()
    if source_mode == "local":
        return _local_runtime_config()
    if source_mode == "bigquery":
        return _cloud_runtime_config()
    raise ValueError(f"Unsupported FOEHNCAST_FEAST_SOURCE: {source_mode}")


def render_runtime_config(output_path: str | Path | None = None) -> Path:
    repo_path = feast_repo_path()
    destination = (
        Path(output_path) if output_path else feast_runtime_config_path(repo_path)
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    desired_config = resolve_runtime_config()

    if destination.exists():
        try:
            with destination.open("r", encoding="utf-8") as handle:
                current_config = yaml.safe_load(handle)
        except (OSError, yaml.YAMLError):
            current_config = None

        # The app and Airflow containers may share this file through a bind
        # mount while running under different UIDs. If the rendered config is
        # already correct, reuse it instead of forcing another rewrite.
        if current_config == desired_config:
            return destination

    # In the local stack multiple containers may render the same runtime file.
    # If another container created it with a restrictive mode, remove it first
    # so this process can recreate a writable copy via the shared bind mount.
    if destination.exists() and not os.access(destination, os.W_OK):
        destination.unlink()

    with destination.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(desired_config, handle, sort_keys=False)

    # A different container UID may still be able to rewrite the file through
    # the shared bind mount while not being allowed to change its mode.
    try:
        destination.chmod(0o666)
    except PermissionError:
        pass

    return destination


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=None)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    print(render_runtime_config(args.output))


if __name__ == "__main__":
    main()
