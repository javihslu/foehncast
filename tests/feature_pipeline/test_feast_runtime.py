"""Tests for the rendered Feast runtime configuration."""

from __future__ import annotations

from pathlib import Path

import yaml

from foehncast import feast_runtime

_LOCAL_DEFAULT_CONFIG = {
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


def test_feast_repo_path_uses_project_root_when_repo_override_is_missing(
    monkeypatch, tmp_path: Path
) -> None:
    repo_path = tmp_path / "feature_repo"
    repo_path.mkdir()
    (tmp_path / "config.yaml").write_text("storage: {}\n")
    (repo_path / "feature_store.yaml").write_text("project: foehncast\n")
    monkeypatch.delenv("FOEHNCAST_FEAST_REPO_PATH", raising=False)
    monkeypatch.setenv("FOEHNCAST_PROJECT_ROOT", str(tmp_path))

    assert feast_runtime.feast_repo_path() == repo_path


def test_render_runtime_config_uses_local_defaults(monkeypatch, tmp_path: Path) -> None:
    repo_path = tmp_path / "feature_repo"
    repo_path.mkdir()

    monkeypatch.setenv("FOEHNCAST_FEAST_REPO_PATH", str(repo_path))
    monkeypatch.delenv("FOEHNCAST_FEAST_SOURCE", raising=False)
    monkeypatch.delenv("FOEHNCAST_FEAST_CONFIG_PATH", raising=False)

    destination = feast_runtime.render_runtime_config()

    assert destination == tmp_path / ".state" / "feast" / "feature_store.runtime.yaml"
    rendered = yaml.safe_load(destination.read_text())
    assert rendered == _LOCAL_DEFAULT_CONFIG


def test_render_runtime_config_uses_bigquery_bindings(
    monkeypatch, tmp_path: Path
) -> None:
    repo_path = tmp_path / "feature_repo"
    repo_path.mkdir()

    monkeypatch.setenv("FOEHNCAST_FEAST_REPO_PATH", str(repo_path))
    monkeypatch.setenv("FOEHNCAST_FEAST_SOURCE", "bigquery")
    monkeypatch.setenv("GCP_PROJECT_ID", "demo-project")
    monkeypatch.setenv("FOEHNCAST_FEAST_GCS_BUCKET", "demo-bucket")
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


def test_render_runtime_config_uses_hosted_contract_defaults(
    monkeypatch, tmp_path: Path
) -> None:
    repo_path = tmp_path / "feature_repo"
    repo_path.mkdir()

    monkeypatch.setenv("FOEHNCAST_FEAST_REPO_PATH", str(repo_path))
    monkeypatch.setenv("FOEHNCAST_FEAST_SOURCE", "bigquery")
    monkeypatch.setenv("GCP_PROJECT_ID", "demo-project")
    monkeypatch.setenv("FOEHNCAST_FEAST_GCS_BUCKET", "demo-bucket")
    monkeypatch.delenv("FOEHNCAST_FEAST_BIGQUERY_DATASET", raising=False)
    monkeypatch.delenv("FOEHNCAST_FEAST_BIGQUERY_LOCATION", raising=False)
    monkeypatch.delenv("FOEHNCAST_FEAST_DATASTORE_DATABASE", raising=False)

    destination = feast_runtime.render_runtime_config()

    rendered = yaml.safe_load(destination.read_text())
    assert rendered["registry"] == "gs://demo-bucket/feast/registry.db"
    assert rendered["offline_store"] == {
        "type": "bigquery",
        "project_id": "demo-project",
        "dataset": "foehncast",
        "location": "EU",
        "gcs_staging_location": "gs://demo-bucket/feast/staging",
    }
    assert rendered["online_store"] == {
        "type": "datastore",
        "project_id": "demo-project",
        "database": "feast-online",
    }


def test_render_runtime_config_allows_datastore_overrides(
    monkeypatch, tmp_path: Path
) -> None:
    repo_path = tmp_path / "feature_repo"
    repo_path.mkdir()

    monkeypatch.setenv("FOEHNCAST_FEAST_REPO_PATH", str(repo_path))
    monkeypatch.setenv("FOEHNCAST_FEAST_SOURCE", "bigquery")
    monkeypatch.setenv("GCP_PROJECT_ID", "demo-project")
    monkeypatch.setenv("FOEHNCAST_FEAST_GCS_BUCKET", "demo-bucket")
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


def test_render_runtime_config_replaces_non_writable_existing_file(
    monkeypatch, tmp_path: Path
) -> None:
    repo_path = tmp_path / "feature_repo"
    repo_path.mkdir()

    monkeypatch.setenv("FOEHNCAST_FEAST_REPO_PATH", str(repo_path))
    monkeypatch.delenv("FOEHNCAST_FEAST_SOURCE", raising=False)
    monkeypatch.delenv("FOEHNCAST_FEAST_CONFIG_PATH", raising=False)

    destination = tmp_path / ".state" / "feast" / "feature_store.runtime.yaml"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("stale: true\n", encoding="utf-8")
    destination.chmod(0o444)

    rendered_path = feast_runtime.render_runtime_config()

    assert rendered_path == destination
    assert yaml.safe_load(rendered_path.read_text()) == _LOCAL_DEFAULT_CONFIG
    assert rendered_path.stat().st_mode & 0o222
