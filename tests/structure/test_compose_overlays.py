"""Structural checks for the local and cloud compose overlays."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
OBJECTSTORE_OVERLAY = REPO_ROOT / "docker-compose.objectstore.yml"
GCP_OVERLAY = REPO_ROOT / "docker-compose.gcp.yml"


@pytest.fixture(scope="module")
def objectstore_overlay() -> dict:
    return yaml.safe_load(OBJECTSTORE_OVERLAY.read_text())


@pytest.fixture(scope="module")
def gcp_overlay() -> dict:
    return yaml.safe_load(GCP_OVERLAY.read_text())


def test_local_registry_artifacts_cannot_be_redirected_by_env(
    objectstore_overlay: dict,
) -> None:
    """A cloud .env must not steer the local registry away from MinIO."""
    destination = objectstore_overlay["services"]["model-registry"]["environment"][
        "MLFLOW_ARTIFACT_DESTINATION"
    ]

    assert destination.startswith("s3://")
    assert "MLFLOW_ARTIFACT_DESTINATION" not in destination


def test_local_feast_cannot_be_redirected_by_env(objectstore_overlay: dict) -> None:
    """A cloud .env must not steer local Feast to BigQuery or a GCS registry."""
    feast_env = objectstore_overlay["x-feast-runtime-env"]

    assert feast_env["FOEHNCAST_FEAST_SOURCE"] == "local"
    assert feast_env["FOEHNCAST_FEAST_REGISTRY"] == ""


def test_cloud_overlay_still_stores_artifacts_in_gcs(gcp_overlay: dict) -> None:
    destination = gcp_overlay["services"]["model-registry"]["environment"][
        "MLFLOW_ARTIFACT_DESTINATION"
    ]

    assert destination.startswith("gs://")
