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
        "candidate_alias": "candidate",
        "champion_alias": "champion",
    }


def _patch_registry_mlflow(
    monkeypatch: pytest.MonkeyPatch,
    mlflow_config: dict[str, str],
    mlflow_stub: object,
) -> None:
    monkeypatch.setattr(register, "mlflow", mlflow_stub)
    monkeypatch.setattr(register, "get_mlflow_config", lambda: mlflow_config)
    monkeypatch.setattr(
        register,
        "get_mlflow_tracking_uri",
        lambda: mlflow_config["tracking_uri"],
    )


class _AliasSettingClient:
    def __init__(self, logged: dict[str, object]) -> None:
        self._logged = logged

    def set_registered_model_alias(
        self, model_name: str, alias: str, version: str
    ) -> None:
        self._logged["alias"] = (model_name, alias, version)


class _AliasSettingMlflow:
    def __init__(self, logged: dict[str, object]) -> None:
        self._logged = logged

    def set_tracking_uri(self, tracking_uri: str) -> None:
        self._logged["tracking_uri"] = tracking_uri

    def MlflowClient(self) -> _AliasSettingClient:
        return _AliasSettingClient(self._logged)


class _ModelLoadingPyfunc:
    def __init__(self, logged: dict[str, str], expected_model: object) -> None:
        self._logged = logged
        self._expected_model = expected_model

    def load_model(self, model_uri: str) -> object:
        self._logged["model_uri"] = model_uri
        return self._expected_model


class _ModelLoadingMlflow:
    def __init__(self, logged: dict[str, str], expected_model: object) -> None:
        self._logged = logged
        self.pyfunc = _ModelLoadingPyfunc(logged, expected_model)

    def set_tracking_uri(self, tracking_uri: str) -> None:
        self._logged["tracking_uri"] = tracking_uri


def test_register_model_registers_logged_model_uri_when_available(
    monkeypatch: pytest.MonkeyPatch, mlflow_config: dict[str, str]
) -> None:
    logged: dict[str, object] = {}
    expected_version = SimpleNamespace(name="foehncast-quality", version="3")

    class FakeClient:
        def get_run(self, run_id: str) -> object:
            logged["run_id"] = run_id
            return SimpleNamespace(info=SimpleNamespace(experiment_id="exp-123"))

        def search_logged_models(
            self,
            experiment_ids: list[str],
            filter_string: str | None = None,
            max_results: int | None = None,
        ) -> list[object]:
            logged["search"] = (experiment_ids, filter_string, max_results)
            return [SimpleNamespace(name="model", model_uri="models:/m-123")]

    class FakeMlflow:
        def set_tracking_uri(self, tracking_uri: str) -> None:
            logged["tracking_uri"] = tracking_uri

        def MlflowClient(self) -> FakeClient:
            return FakeClient()

        def register_model(self, model_uri: str, model_name: str) -> object:
            logged["registration"] = (model_uri, model_name)
            return expected_version

    _patch_registry_mlflow(monkeypatch, mlflow_config, FakeMlflow())

    model_version = register.register_model("run-123")

    assert model_version is expected_version
    assert logged["tracking_uri"] == "http://localhost:5001"
    assert logged["run_id"] == "run-123"
    assert logged["search"] == (
        ["exp-123"],
        "source_run_id = 'run-123'",
        20,
    )
    assert logged["registration"] == (
        "models:/m-123",
        "foehncast-quality",
    )


def test_register_model_allows_model_name_override(
    monkeypatch: pytest.MonkeyPatch, mlflow_config: dict[str, str]
) -> None:
    logged: dict[str, tuple[str, str]] = {}

    class FakeClient:
        def get_run(self, run_id: str) -> object:
            return SimpleNamespace(info=SimpleNamespace(experiment_id="exp-123"))

        def search_logged_models(
            self,
            experiment_ids: list[str],
            filter_string: str | None = None,
            max_results: int | None = None,
        ) -> list[object]:
            return [SimpleNamespace(name="model", model_uri="models:/m-456")]

    class FakeMlflow:
        def set_tracking_uri(self, tracking_uri: str) -> None:
            return None

        def MlflowClient(self) -> FakeClient:
            return FakeClient()

        def register_model(self, model_uri: str, model_name: str) -> object:
            logged["registration"] = (model_uri, model_name)
            return object()

    _patch_registry_mlflow(monkeypatch, mlflow_config, FakeMlflow())

    register.register_model("run-456", model_name="foehncast-experiment")

    assert logged["registration"] == (
        "models:/m-456",
        "foehncast-experiment",
    )


def test_register_model_falls_back_to_run_artifact_when_logged_model_lookup_is_unavailable(
    monkeypatch: pytest.MonkeyPatch, mlflow_config: dict[str, str]
) -> None:
    logged: dict[str, tuple[str, str]] = {}

    class FakeClient:
        pass

    class FakeMlflow:
        def set_tracking_uri(self, tracking_uri: str) -> None:
            return None

        def MlflowClient(self) -> FakeClient:
            return FakeClient()

        def register_model(self, model_uri: str, model_name: str) -> object:
            logged["registration"] = (model_uri, model_name)
            return object()

    _patch_registry_mlflow(monkeypatch, mlflow_config, FakeMlflow())

    register.register_model("run-789")

    assert logged["registration"] == (
        "runs:/run-789/model",
        "foehncast-quality",
    )


def test_promote_model_assigns_champion_alias_for_production(
    monkeypatch: pytest.MonkeyPatch, mlflow_config: dict[str, str]
) -> None:
    logged: dict[str, object] = {}

    _patch_registry_mlflow(monkeypatch, mlflow_config, _AliasSettingMlflow(logged))

    register.promote_model(None, 7)

    assert logged["tracking_uri"] == "http://localhost:5001"
    assert logged["alias"] == ("foehncast-quality", "champion", "7")


def test_promote_model_assigns_candidate_alias_for_candidate_stage(
    monkeypatch: pytest.MonkeyPatch, mlflow_config: dict[str, str]
) -> None:
    logged: dict[str, object] = {}

    _patch_registry_mlflow(monkeypatch, mlflow_config, _AliasSettingMlflow(logged))

    register.promote_model(None, 11, stage="Candidate")

    assert logged["tracking_uri"] == "http://localhost:5001"
    assert logged["alias"] == ("foehncast-quality", "candidate", "11")


def test_get_production_model_loads_model_from_champion_alias(
    monkeypatch: pytest.MonkeyPatch, mlflow_config: dict[str, str]
) -> None:
    logged: dict[str, str] = {}
    expected_model = object()

    _patch_registry_mlflow(
        monkeypatch,
        mlflow_config,
        _ModelLoadingMlflow(logged, expected_model),
    )

    model = register.get_production_model()

    assert model is expected_model
    assert logged["tracking_uri"] == "http://localhost:5001"
    assert logged["model_uri"] == "models:/foehncast-quality@champion"


def test_get_model_by_alias_loads_requested_alias(
    monkeypatch: pytest.MonkeyPatch, mlflow_config: dict[str, str]
) -> None:
    logged: dict[str, str] = {}
    expected_model = object()

    _patch_registry_mlflow(
        monkeypatch,
        mlflow_config,
        _ModelLoadingMlflow(logged, expected_model),
    )

    model = register.get_model_by_alias("candidate")

    assert model is expected_model
    assert logged["tracking_uri"] == "http://localhost:5001"
    assert logged["model_uri"] == "models:/foehncast-quality@candidate"


def test_assign_model_alias_sets_explicit_alias(
    monkeypatch: pytest.MonkeyPatch, mlflow_config: dict[str, str]
) -> None:
    logged: dict[str, object] = {}

    _patch_registry_mlflow(monkeypatch, mlflow_config, _AliasSettingMlflow(logged))

    register.assign_model_alias("champion", 13)

    assert logged["tracking_uri"] == "http://localhost:5001"
    assert logged["alias"] == ("foehncast-quality", "champion", "13")


def test_assign_model_alias_requires_non_empty_alias_and_version() -> None:
    with pytest.raises(ValueError, match="Model alias must be non-empty"):
        register.assign_model_alias("   ", 13)

    with pytest.raises(ValueError, match="Model version must be non-empty"):
        register.assign_model_alias("champion", "   ")
