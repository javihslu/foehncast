"""Shared pytest fixtures for MLflow-related tests."""

from __future__ import annotations

import pytest


def clear_tracking_uri_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)


@pytest.fixture(autouse=True)
def clear_tracking_uri(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_tracking_uri_env(monkeypatch)
