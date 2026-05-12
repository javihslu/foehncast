"""Tests for configuration loading and environment overrides."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from foehncast import config


@pytest.fixture(autouse=True)
def reset_config_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "_config", None)
    for name in (
        "FOEHNCAST_CONFIG_PATH",
        "FOEHNCAST_PROJECT_ROOT",
        "STORAGE_BACKEND",
        "STORAGE_S3_BUCKET",
        "STORAGE_S3_ENDPOINT",
        "OBJECTSTORE_BUCKET",
        "STORAGE_BIGQUERY_PROJECT_ID",
        "STORAGE_BIGQUERY_DATASET",
        "STORAGE_BIGQUERY_TABLE",
        "GCP_PROJECT_ID",
        "GOOGLE_CLOUD_PROJECT",
        "MLFLOW_TRACKING_URI",
        "OBJECTSTORE_ENDPOINT",
        "FSSPEC_S3_ENDPOINT_URL",
    ):
        monkeypatch.delenv(name, raising=False)


def _write_config(path: Path) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "storage": {"backend": "s3"},
                "mlflow": {
                    "experiment_name": "foehncast",
                    "model_name": "foehncast-quality",
                    "candidate_alias": "candidate",
                    "champion_alias": "champion",
                },
            },
            sort_keys=False,
        )
    )


def _write_legacy_runtime_config(path: Path) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "storage": {
                    "backend": "s3",
                    "s3_bucket": "legacy-bucket",
                    "s3_endpoint": "http://legacy-objectstore:9000",
                    "bigquery_project_id": "yaml-project",
                    "bigquery_dataset": "yaml_dataset",
                    "bigquery_table": "yaml_table",
                },
                "mlflow": {
                    "tracking_uri": "http://legacy-mlflow:5001",
                    "experiment_name": "foehncast",
                    "model_name": "foehncast-quality",
                    "candidate_alias": "candidate",
                    "champion_alias": "champion",
                },
            },
            sort_keys=False,
        )
    )


def test_storage_env_overrides_apply_after_initial_load(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(config_path)

    initial = config.load_config(config_path)
    assert initial["storage"]["backend"] == "s3"

    monkeypatch.setenv("STORAGE_BACKEND", "bigquery")
    monkeypatch.setenv("STORAGE_BIGQUERY_DATASET", "cloud_features")
    monkeypatch.setenv("STORAGE_BIGQUERY_TABLE", "train_rows")
    monkeypatch.setenv("GCP_PROJECT_ID", "env-project")

    storage_config = config.get_storage_config()

    assert storage_config["backend"] == "bigquery"
    assert storage_config["bigquery_dataset"] == "cloud_features"
    assert storage_config["bigquery_table"] == "train_rows"
    assert storage_config["bigquery_project_id"] == "env-project"
    assert config.load_config()["storage"] == {"backend": "s3"}


def test_runtime_resolution_does_not_mutate_cached_yaml_values(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(config_path)

    config.load_config(config_path)

    monkeypatch.setenv("GCP_PROJECT_ID", "env-project")
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "https://mlflow.example.com")

    cached = config.load_config()
    assert cached["storage"] == {"backend": "s3"}
    assert "tracking_uri" not in cached["mlflow"]
    assert config.get_storage_config()["bigquery_project_id"] == "env-project"
    assert config.get_mlflow_tracking_uri() == "https://mlflow.example.com"

    monkeypatch.delenv("GCP_PROJECT_ID")
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("MLFLOW_TRACKING_URI")

    reverted = config.load_config()
    assert reverted["storage"] == {"backend": "s3"}
    assert "bigquery_project_id" not in config.get_storage_config()
    assert config.get_storage_config()["bigquery_dataset"] == "foehncast"
    assert config.get_storage_config()["bigquery_table"] == "forecast_features"
    assert config.get_mlflow_tracking_uri() == "http://localhost:5001"


def test_objectstore_bucket_overrides_s3_bucket(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(config_path)

    config.load_config(config_path)
    monkeypatch.setenv("OBJECTSTORE_BUCKET", "compatibility-bucket")

    storage_config = config.get_storage_config()

    assert storage_config["s3_bucket"] == "compatibility-bucket"


def test_legacy_runtime_fields_still_resolve_without_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config_path = tmp_path / "config.yaml"
    _write_legacy_runtime_config(config_path)

    config.load_config(config_path)

    storage_config = config.get_storage_config()

    assert storage_config["s3_bucket"] == "legacy-bucket"
    assert storage_config["s3_endpoint"] == "http://legacy-objectstore:9000"
    assert storage_config["bigquery_project_id"] == "yaml-project"
    assert storage_config["bigquery_dataset"] == "yaml_dataset"
    assert storage_config["bigquery_table"] == "yaml_table"
    assert config.get_mlflow_tracking_uri() == "http://legacy-mlflow:5001"


def test_project_root_env_resolves_default_config_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(config_path)
    monkeypatch.setenv("FOEHNCAST_PROJECT_ROOT", str(tmp_path))

    loaded = config.load_config()

    assert loaded["storage"]["backend"] == "s3"
