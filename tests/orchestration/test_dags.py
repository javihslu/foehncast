"""Tests for Airflow DAG wiring and schedule configuration."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

from foehncast.airflow_assets import (
    curated_feature_store_asset_uri,
    drift_report_asset_uri,
    feast_feature_store_asset_uri,
    mlflow_evaluation_asset_uri,
    mlflow_registry_asset_uri,
    mlflow_training_run_asset_uri,
    training_request_asset_uri,
)

_ROOT = Path(__file__).resolve().parent.parent.parent


def _load_dag_module(
    monkeypatch: pytest.MonkeyPatch,
    relative_path: str,
    *,
    env: dict[str, str | None] | None = None,
) -> tuple[types.ModuleType, list[object]]:
    path = _ROOT / relative_path
    operators: list[object] = []

    class FakeDAG:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

        def __enter__(self) -> FakeDAG:
            return self

        def __exit__(self, exc_type, exc, exc_tb) -> None:
            return None

    class FakeAsset:
        def __init__(
            self, name: str | None = None, uri: str | None = None, **kwargs: object
        ) -> None:
            self.name = name
            self.uri = uri
            self.kwargs = kwargs

    class FakePythonOperator:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs
            self.output = f"output:{kwargs['task_id']}"
            operators.append(self)

        def __rshift__(self, other: object) -> object:
            return other

    airflow_module = types.ModuleType("airflow")
    airflow_module.__path__ = []
    sdk_module = types.ModuleType("airflow.sdk")
    sdk_module.Asset = FakeAsset
    sdk_module.DAG = FakeDAG
    providers_module = types.ModuleType("airflow.providers")
    providers_module.__path__ = []
    standard_module = types.ModuleType("airflow.providers.standard")
    standard_module.__path__ = []
    operators_module = types.ModuleType("airflow.providers.standard.operators")
    operators_module.__path__ = []
    empty_module = types.ModuleType("airflow.providers.standard.operators.empty")
    python_module = types.ModuleType("airflow.providers.standard.operators.python")
    empty_module.EmptyOperator = FakePythonOperator
    python_module.PythonOperator = FakePythonOperator
    python_module.ShortCircuitOperator = FakePythonOperator

    monkeypatch.setitem(sys.modules, "airflow", airflow_module)
    monkeypatch.setitem(sys.modules, "airflow.sdk", sdk_module)
    monkeypatch.setitem(sys.modules, "airflow.providers", providers_module)
    monkeypatch.setitem(sys.modules, "airflow.providers.standard", standard_module)
    monkeypatch.setitem(
        sys.modules, "airflow.providers.standard.operators", operators_module
    )
    monkeypatch.setitem(
        sys.modules, "airflow.providers.standard.operators.empty", empty_module
    )
    monkeypatch.setitem(
        sys.modules, "airflow.providers.standard.operators.python", python_module
    )

    for name in (
        "AIRFLOW_FEATURE_DATASET",
        "AIRFLOW_FEATURE_SCHEDULE",
        "AIRFLOW_AUTO_RETRAIN_MODE",
        "AIRFLOW_TRAINING_DATASET",
        "AIRFLOW_DRIFT_DATASET",
        "AIRFLOW_DRIFT_SCHEDULE",
    ):
        monkeypatch.delenv(name, raising=False)

    if env:
        for name, value in env.items():
            if value is None:
                monkeypatch.delenv(name, raising=False)
            else:
                monkeypatch.setenv(name, value)

    spec = importlib.util.spec_from_file_location(f"test_{path.stem}", path)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, operators


def test_feature_dag_defaults_to_airflow_schedule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, operators = _load_dag_module(monkeypatch, "dags/feature_dag.py")

    assert module.dag.kwargs["schedule"] == "0 */6 * * *"
    assert module.dag.kwargs["catchup"] is False
    assert module.dag.kwargs["is_paused_upon_creation"] is False
    assert [operator.kwargs["task_id"] for operator in operators] == [
        "fetch_feature_inputs",
        "engineer_feature_set",
        "validate_feature_set",
        "store_feature_set",
        "prepare_feast_feature_store",
        "check_retraining_trigger",
        "publish_training_request",
    ]
    assert operators[0].kwargs["op_kwargs"] == {
        "dataset": "train",
        "run_key": "{{ run_id }}",
    }
    assert operators[1].kwargs["op_args"] == ["output:fetch_feature_inputs"]
    assert operators[2].kwargs["op_args"] == ["output:engineer_feature_set"]
    assert operators[3].kwargs["op_args"] == ["output:validate_feature_set"]
    assert operators[3].kwargs["op_kwargs"] == {
        "auto_retraining_mode": "always",
        "training_request_stage": "Production",
    }
    assert operators[4].kwargs["op_kwargs"] == {"dataset": "train"}
    assert [asset.uri for asset in operators[4].kwargs["outlets"]] == [
        curated_feature_store_asset_uri("train"),
        feast_feature_store_asset_uri("train"),
    ]
    assert operators[5].kwargs["op_kwargs"] == {
        "feature_result": "output:store_feature_set",
        "mode": "always",
    }
    assert [asset.uri for asset in operators[6].kwargs["outlets"]] == [
        training_request_asset_uri("train", stage="production"),
    ]


def test_feature_dag_supports_manual_override_dataset_and_disabled_retraining(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, operators = _load_dag_module(
        monkeypatch,
        "dags/feature_dag.py",
        env={
            "AIRFLOW_FEATURE_DATASET": "validation",
            "AIRFLOW_FEATURE_SCHEDULE": "manual",
            "AIRFLOW_AUTO_RETRAIN_MODE": "off",
        },
    )

    assert module.dag.kwargs["schedule"] is None
    assert [operator.kwargs["task_id"] for operator in operators] == [
        "fetch_feature_inputs",
        "engineer_feature_set",
        "validate_feature_set",
        "store_feature_set",
        "prepare_feast_feature_store",
    ]
    assert operators[0].kwargs["op_kwargs"] == {
        "dataset": "validation",
        "run_key": "{{ run_id }}",
    }
    assert operators[3].kwargs["op_kwargs"] == {
        "auto_retraining_mode": None,
        "training_request_stage": "Production",
    }
    assert operators[4].kwargs["op_kwargs"] == {"dataset": "validation"}


def test_training_dag_is_asset_scheduled_and_active_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, operators = _load_dag_module(monkeypatch, "dags/training_dag.py")

    assert [asset.uri for asset in module.dag.kwargs["schedule"]] == [
        training_request_asset_uri("train", stage="production"),
    ]
    assert module.dag.kwargs["catchup"] is False
    assert module.dag.kwargs["is_paused_upon_creation"] is False
    assert module.dag.kwargs["params"] == {"dataset": "train"}
    assert [operator.kwargs["task_id"] for operator in operators] == [
        "train_model",
        "evaluate_model",
        "register_model",
    ]
    expected_dataset_template = (
        "{{ dag_run.conf.get('dataset') if dag_run and dag_run.conf and "
        "dag_run.conf.get('dataset') else params.dataset }}"
    )
    expected_stage_template = (
        "{{ dag_run.conf.get('stage') if dag_run and dag_run.conf and "
        "dag_run.conf.get('stage') else 'Candidate' }}"
    )
    assert operators[0].kwargs["op_kwargs"] == {
        "dataset": expected_dataset_template,
        "requested_stage": expected_stage_template,
    }
    assert operators[1].kwargs["op_kwargs"] == {
        "dataset": expected_dataset_template,
        "requested_stage": expected_stage_template,
    }
    assert operators[2].kwargs["op_kwargs"] == {
        "stage": expected_stage_template,
        "dataset": expected_dataset_template,
    }
    assert [asset.uri for asset in operators[0].kwargs["inlets"]] == [
        curated_feature_store_asset_uri("train"),
        training_request_asset_uri("train", stage="production"),
    ]
    assert [asset.uri for asset in operators[0].kwargs["outlets"]] == [
        mlflow_training_run_asset_uri("train"),
    ]
    assert [asset.uri for asset in operators[1].kwargs["inlets"]] == [
        mlflow_training_run_asset_uri("train"),
    ]
    assert [asset.uri for asset in operators[1].kwargs["outlets"]] == [
        mlflow_evaluation_asset_uri("train"),
    ]
    assert [asset.uri for asset in operators[2].kwargs["inlets"]] == [
        mlflow_training_run_asset_uri("train"),
        mlflow_evaluation_asset_uri("train"),
    ]
    assert [asset.uri for asset in operators[2].kwargs["outlets"]] == [
        mlflow_registry_asset_uri(),
    ]


def test_training_dag_supports_dataset_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, operators = _load_dag_module(
        monkeypatch,
        "dags/training_dag.py",
        env={"AIRFLOW_TRAINING_DATASET": "validation"},
    )

    assert module.dag.kwargs["params"] == {"dataset": "validation"}
    expected_dataset_template = (
        "{{ dag_run.conf.get('dataset') if dag_run and dag_run.conf and "
        "dag_run.conf.get('dataset') else params.dataset }}"
    )
    expected_stage_template = (
        "{{ dag_run.conf.get('stage') if dag_run and dag_run.conf and "
        "dag_run.conf.get('stage') else 'Candidate' }}"
    )
    assert operators[0].kwargs["op_kwargs"] == {
        "dataset": expected_dataset_template,
        "requested_stage": expected_stage_template,
    }
    assert operators[1].kwargs["op_kwargs"] == {
        "dataset": expected_dataset_template,
        "requested_stage": expected_stage_template,
    }


def test_runtime_release_dag_accepts_manual_handoff_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, operators = _load_dag_module(monkeypatch, "dags/runtime_release_dag.py")

    assert module.dag.kwargs["schedule"] is None
    assert module.dag.kwargs["catchup"] is False
    assert module.dag.kwargs["is_paused_upon_creation"] is False
    assert module.dag.kwargs["tags"] == ["foehncast", "runtime"]
    assert [operator.kwargs["task_id"] for operator in operators] == [
        "record_runtime_release_request",
    ]
    assert operators[0].kwargs["op_kwargs"] == {
        "request_json": "{{ dag_run.conf | tojson if dag_run and dag_run.conf else '{}' }}",
        "dag_run_id": "{{ run_id }}",
        "dag_id": "runtime_release",
    }


def test_drift_dag_defaults_to_twelve_hour_schedule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AIRFLOW_DRIFT_DATASET", raising=False)
    monkeypatch.delenv("AIRFLOW_DRIFT_SCHEDULE", raising=False)
    module, operators = _load_dag_module(monkeypatch, "dags/drift_dag.py")

    assert module.dag.kwargs["schedule"] == "0 */12 * * *"
    assert module.dag.kwargs["catchup"] is False
    assert module.dag.kwargs["is_paused_upon_creation"] is False
    assert module.dag.kwargs["tags"] == ["foehncast", "monitoring"]
    assert [operator.kwargs["task_id"] for operator in operators] == [
        "detect_feature_drift",
        "detect_prediction_drift",
    ]
    assert operators[0].kwargs["op_kwargs"] == {"dataset": "train"}
    assert [asset.uri for asset in operators[0].kwargs["outlets"]] == [
        drift_report_asset_uri("train"),
    ]
    assert [asset.uri for asset in operators[1].kwargs["outlets"]] == [
        drift_report_asset_uri("train"),
    ]


def test_drift_dag_supports_custom_schedule_and_dataset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, operators = _load_dag_module(
        monkeypatch,
        "dags/drift_dag.py",
        env={
            "AIRFLOW_DRIFT_DATASET": "validation",
            "AIRFLOW_DRIFT_SCHEDULE": "0 0 * * *",
        },
    )

    assert module.dag.kwargs["schedule"] == "0 0 * * *"
    assert operators[0].kwargs["op_kwargs"] == {"dataset": "validation"}
    assert [asset.uri for asset in operators[0].kwargs["outlets"]] == [
        drift_report_asset_uri("validation"),
    ]


def test_drift_dag_can_be_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, _operators = _load_dag_module(
        monkeypatch,
        "dags/drift_dag.py",
        env={"AIRFLOW_DRIFT_SCHEDULE": "manual"},
    )

    assert module.dag.kwargs["schedule"] is None
