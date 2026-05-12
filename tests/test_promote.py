"""Tests for model promotion helpers."""

from __future__ import annotations

import pytest

from foehncast.training_pipeline import promote


@pytest.fixture(autouse=True)
def _clear_tracking_uri(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)


@pytest.fixture()
def mlflow_config() -> dict[str, str]:
    return {
        "tracking_uri": "http://localhost:5001",
        "model_name": "foehncast-quality",
        "candidate_alias": "candidate",
        "champion_alias": "champion",
    }


def test_resolve_model_version_by_alias_reads_registered_model_version(
    monkeypatch: pytest.MonkeyPatch, mlflow_config: dict[str, str]
) -> None:
    logged: dict[str, object] = {}

    class FakeClient:
        def get_model_version_by_alias(self, model_name: str, alias: str) -> object:
            logged["lookup"] = (model_name, alias)
            return type("FakeVersion", (), {"version": "11"})()

    class FakeMlflow:
        def set_tracking_uri(self, tracking_uri: str) -> None:
            logged["tracking_uri"] = tracking_uri

        def MlflowClient(self) -> FakeClient:
            return FakeClient()

    monkeypatch.setattr(promote, "mlflow", FakeMlflow())
    monkeypatch.setattr(promote, "get_mlflow_config", lambda: mlflow_config)
    monkeypatch.setattr(
        promote, "get_mlflow_tracking_uri", lambda: "http://localhost:5001"
    )

    version = promote.resolve_model_version_by_alias("candidate")

    assert version == "11"
    assert logged["tracking_uri"] == "http://localhost:5001"
    assert logged["lookup"] == ("foehncast-quality", "candidate")


def test_promote_model_version_assigns_stage_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logged: dict[str, object] = {}

    monkeypatch.setattr(
        promote,
        "promote_model",
        lambda model_name, version, stage="Production": logged.update(
            {"promotion": (model_name, version, stage)}
        ),
    )

    version = promote.promote_model_version("7")

    assert version == "7"
    assert logged["promotion"] == (None, "7", "Production")


def test_promote_model_alias_promotes_resolved_alias_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logged: dict[str, object] = {}

    monkeypatch.setattr(
        promote,
        "resolve_model_version_by_alias",
        lambda alias, model_name=None: "19",
    )
    monkeypatch.setattr(
        promote,
        "promote_model",
        lambda model_name, version, stage="Production": logged.update(
            {"promotion": (model_name, version, stage)}
        ),
    )

    version = promote.promote_model_alias("candidate")

    assert version == "19"
    assert logged["promotion"] == (None, "19", "Production")
