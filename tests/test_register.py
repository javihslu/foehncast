"""Tests for the MLflow model registry helpers."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from foehncast.training_pipeline import register


@pytest.fixture()
def mlflow_config() -> dict[str, str]:
    return {
        "tracking_uri": "http://localhost:5001",
        "model_name": "foehncast-quality",
        "champion_alias": "champion",
    }


def test_register_model_registers_run_artifact(
    monkeypatch: pytest.MonkeyPatch, mlflow_config: dict[str, str]
) -> None:
    logged: dict[str, object] = {}
    expected_version = SimpleNamespace(name="foehncast-quality", version="3")

    class FakeMlflow:
        def set_tracking_uri(self, tracking_uri: str) -> None:
            logged["tracking_uri"] = tracking_uri

        def register_model(self, model_uri: str, model_name: str) -> object:
            logged["registration"] = (model_uri, model_name)
            return expected_version

    monkeypatch.setattr(register, "mlflow", FakeMlflow())
    monkeypatch.setattr(register, "get_mlflow_config", lambda: mlflow_config)

    model_version = register.register_model("run-123")

    assert model_version is expected_version
    assert logged["tracking_uri"] == "http://localhost:5001"
    assert logged["registration"] == (
        "runs:/run-123/model",
        "foehncast-quality",
    )


def test_register_model_allows_model_name_override(
    monkeypatch: pytest.MonkeyPatch, mlflow_config: dict[str, str]
) -> None:
    logged: dict[str, tuple[str, str]] = {}

    class FakeMlflow:
        def set_tracking_uri(self, tracking_uri: str) -> None:
            return None

        def register_model(self, model_uri: str, model_name: str) -> object:
            logged["registration"] = (model_uri, model_name)
            return object()

    monkeypatch.setattr(register, "mlflow", FakeMlflow())
    monkeypatch.setattr(register, "get_mlflow_config", lambda: mlflow_config)

    register.register_model("run-456", model_name="foehncast-experiment")

    assert logged["registration"] == (
        "runs:/run-456/model",
        "foehncast-experiment",
    )


def test_promote_model_assigns_champion_alias_for_production(
    monkeypatch: pytest.MonkeyPatch, mlflow_config: dict[str, str]
) -> None:
    logged: dict[str, object] = {}

    class FakeClient:
        def set_registered_model_alias(
            self, model_name: str, alias: str, version: str
        ) -> None:
            logged["alias"] = (model_name, alias, version)

    class FakeMlflow:
        def set_tracking_uri(self, tracking_uri: str) -> None:
            logged["tracking_uri"] = tracking_uri

        def MlflowClient(self) -> FakeClient:
            return FakeClient()

    monkeypatch.setattr(register, "mlflow", FakeMlflow())
    monkeypatch.setattr(register, "get_mlflow_config", lambda: mlflow_config)

    register.promote_model(None, 7)

    assert logged["tracking_uri"] == "http://localhost:5001"
    assert logged["alias"] == ("foehncast-quality", "champion", "7")


def test_get_production_model_loads_model_from_champion_alias(
    monkeypatch: pytest.MonkeyPatch, mlflow_config: dict[str, str]
) -> None:
    logged: dict[str, str] = {}
    expected_model = object()

    class FakePyfunc:
        def load_model(self, model_uri: str) -> object:
            logged["model_uri"] = model_uri
            return expected_model

    class FakeMlflow:
        pyfunc = FakePyfunc()

        def set_tracking_uri(self, tracking_uri: str) -> None:
            logged["tracking_uri"] = tracking_uri

    monkeypatch.setattr(register, "mlflow", FakeMlflow())
    monkeypatch.setattr(register, "get_mlflow_config", lambda: mlflow_config)

    model = register.get_production_model()

    assert model is expected_model
    assert logged["tracking_uri"] == "http://localhost:5001"
    assert logged["model_uri"] == "models:/foehncast-quality@champion"
