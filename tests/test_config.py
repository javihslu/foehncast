"""Tests for configuration loading and environment overrides."""

from __future__ import annotations

from pathlib import Path

import pytest

from foehncast import config


@pytest.fixture(autouse=True)
def reset_config_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "_config", None)
    for name in (
        "STORAGE_BACKEND",
        "STORAGE_LOCAL_PATH",
        "STORAGE_S3_BUCKET",
        "STORAGE_S3_ENDPOINT",
        "STORAGE_BIGQUERY_PROJECT_ID",
        "STORAGE_BIGQUERY_DATASET",
        "STORAGE_BIGQUERY_TABLE",
        "GCP_PROJECT_ID",
        "GOOGLE_CLOUD_PROJECT",
        "GCP_LOCATION",
        "GCP_BUCKET_NAME",
        "CLOUD_RUN_SERVICE_NAME",
        "MLFLOW_TRACKING_URI",
        "OBJECTSTORE_ENDPOINT",
        "FSSPEC_S3_ENDPOINT_URL",
    ):
        monkeypatch.delenv(name, raising=False)


def _write_config(path: Path) -> None:
    path.write_text(
        """
storage:
  backend: local
  local_path: data
  s3_bucket: foehncast-data
  s3_endpoint: http://localhost:9000
  bigquery_dataset: foehncast
  bigquery_table: forecast_features
gcp:
  project_id: yaml-project
  location: europe-west6
  bucket_name: yaml-bucket
  cloud_run_service: foehncast-serve
mlflow:
  tracking_uri: http://localhost:5001
""".strip()
    )


def test_storage_env_overrides_apply_after_initial_load(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(config_path)

    initial = config.load_config(config_path)
    assert initial["storage"]["backend"] == "local"

    monkeypatch.setenv("STORAGE_BACKEND", "bigquery")
    monkeypatch.setenv("STORAGE_BIGQUERY_DATASET", "cloud_features")
    monkeypatch.setenv("STORAGE_BIGQUERY_TABLE", "train_rows")
    monkeypatch.setenv("GCP_PROJECT_ID", "env-project")

    storage_config = config.get_storage_config()

    assert storage_config["backend"] == "bigquery"
    assert storage_config["bigquery_dataset"] == "cloud_features"
    assert storage_config["bigquery_table"] == "train_rows"
    assert storage_config["bigquery_project_id"] == "env-project"


def test_env_overrides_do_not_mutate_cached_yaml_values(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(config_path)

    config.load_config(config_path)

    monkeypatch.setenv("GCP_PROJECT_ID", "env-project")
    monkeypatch.setenv("GCP_LOCATION", "us-central1")
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "https://mlflow.example.com")

    overridden = config.load_config()
    assert overridden["gcp"]["project_id"] == "env-project"
    assert overridden["gcp"]["location"] == "us-central1"
    assert overridden["mlflow"]["tracking_uri"] == "https://mlflow.example.com"

    monkeypatch.delenv("GCP_PROJECT_ID")
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("GCP_LOCATION")
    monkeypatch.delenv("MLFLOW_TRACKING_URI")

    reverted = config.load_config()
    assert reverted["gcp"]["project_id"] == "yaml-project"
    assert reverted["gcp"]["location"] == "europe-west6"
    assert reverted["mlflow"]["tracking_uri"] == "http://localhost:5001"
