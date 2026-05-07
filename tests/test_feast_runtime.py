"""Tests for the rendered Feast runtime configuration."""

from __future__ import annotations

from pathlib import Path

import yaml

from foehncast import feast_runtime


def test_render_runtime_config_uses_local_defaults(monkeypatch, tmp_path: Path) -> None:
    repo_path = tmp_path / "feature_repo"
    repo_path.mkdir()

    monkeypatch.setenv("FOEHNCAST_FEAST_REPO_PATH", str(repo_path))
    monkeypatch.delenv("FOEHNCAST_FEAST_SOURCE", raising=False)
    monkeypatch.delenv("FOEHNCAST_FEAST_CONFIG_PATH", raising=False)

    destination = feast_runtime.render_runtime_config()

    assert destination == tmp_path / ".state" / "feast" / "feature_store.runtime.yaml"
    rendered = yaml.safe_load(destination.read_text())
    assert rendered == {
        "project": "foehncast",
        "entity_key_serialization_version": 3,
        "registry": "../.state/feast/registry.db",
        "provider": "gcp",
        "offline_store": {"type": "file"},
        "online_store": {
            "type": "datastore",
            "project_id": "foehncast-local",
        },
    }


def test_render_runtime_config_uses_bigquery_bindings(
    monkeypatch, tmp_path: Path
) -> None:
    repo_path = tmp_path / "feature_repo"
    repo_path.mkdir()

    monkeypatch.setenv("FOEHNCAST_FEAST_REPO_PATH", str(repo_path))
    monkeypatch.setenv("FOEHNCAST_FEAST_SOURCE", "bigquery")
    monkeypatch.setenv("GCP_PROJECT_ID", "demo-project")
    monkeypatch.setenv("GCP_BUCKET_NAME", "demo-bucket")
    monkeypatch.setenv("FOEHNCAST_FEAST_BIGQUERY_DATASET", "feast_runtime")
    monkeypatch.setenv("FOEHNCAST_FEAST_BIGQUERY_LOCATION", "EU")

    destination = feast_runtime.render_runtime_config()

    rendered = yaml.safe_load(destination.read_text())
    assert rendered == {
        "project": "foehncast",
        "entity_key_serialization_version": 3,
        "registry": "gs://demo-bucket/feast/registry.db",
        "provider": "gcp",
        "offline_store": {
            "type": "bigquery",
            "project_id": "demo-project",
            "dataset": "feast_runtime",
            "location": "EU",
            "gcs_staging_location": "gs://demo-bucket/feast/staging",
        },
        "online_store": {
            "type": "datastore",
            "project_id": "demo-project",
            "database": "feast-online",
        },
    }


def test_render_runtime_config_allows_datastore_overrides(
    monkeypatch, tmp_path: Path
) -> None:
    repo_path = tmp_path / "feature_repo"
    repo_path.mkdir()

    monkeypatch.setenv("FOEHNCAST_FEAST_REPO_PATH", str(repo_path))
    monkeypatch.setenv("FOEHNCAST_FEAST_SOURCE", "bigquery")
    monkeypatch.setenv("GCP_PROJECT_ID", "demo-project")
    monkeypatch.setenv("GCP_BUCKET_NAME", "demo-bucket")
    monkeypatch.setenv("FOEHNCAST_FEAST_DATASTORE_DATABASE", "custom-feast-db")
    monkeypatch.setenv("FOEHNCAST_FEAST_DATASTORE_NAMESPACE", "serving")

    destination = feast_runtime.render_runtime_config()

    rendered = yaml.safe_load(destination.read_text())
    assert rendered["online_store"] == {
        "type": "datastore",
        "project_id": "demo-project",
        "database": "custom-feast-db",
        "namespace": "serving",
    }
