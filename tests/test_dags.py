"""Tests for Airflow DAG wiring and schedule configuration."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent


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
    sdk_module.DAG = FakeDAG
    providers_module = types.ModuleType("airflow.providers")
    providers_module.__path__ = []
    standard_module = types.ModuleType("airflow.providers.standard")
    standard_module.__path__ = []
    operators_module = types.ModuleType("airflow.providers.standard.operators")
    operators_module.__path__ = []
    python_module = types.ModuleType("airflow.providers.standard.operators.python")
    trigger_module = types.ModuleType(
        "airflow.providers.standard.operators.trigger_dagrun"
    )
    python_module.PythonOperator = FakePythonOperator
    python_module.ShortCircuitOperator = FakePythonOperator
    trigger_module.TriggerDagRunOperator = FakePythonOperator

    monkeypatch.setitem(sys.modules, "airflow", airflow_module)
    monkeypatch.setitem(sys.modules, "airflow.sdk", sdk_module)
    monkeypatch.setitem(sys.modules, "airflow.providers", providers_module)
    monkeypatch.setitem(sys.modules, "airflow.providers.standard", standard_module)
    monkeypatch.setitem(
        sys.modules, "airflow.providers.standard.operators", operators_module
    )
    monkeypatch.setitem(
        sys.modules, "airflow.providers.standard.operators.python", python_module
    )
    monkeypatch.setitem(
        sys.modules,
        "airflow.providers.standard.operators.trigger_dagrun",
        trigger_module,
    )

    for name in (
        "AIRFLOW_FEATURE_DATASET",
        "AIRFLOW_FEATURE_SCHEDULE",
        "AIRFLOW_AUTO_RETRAIN_MODE",
        "AIRFLOW_TRAINING_DATASET",
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
        "check_retraining_trigger",
        "trigger_training_pipeline",
    ]
    assert operators[0].kwargs["op_kwargs"] == {
        "dataset": "train",
        "run_key": "{{ run_id }}",
    }
    assert operators[1].kwargs["op_args"] == ["output:fetch_feature_inputs"]
    assert operators[2].kwargs["op_args"] == ["output:engineer_feature_set"]
    assert operators[3].kwargs["op_args"] == ["output:validate_feature_set"]
    assert operators[4].kwargs["op_kwargs"] == {
        "feature_result": "output:store_feature_set",
        "mode": "always",
    }
    assert operators[5].kwargs["trigger_dag_id"] == "training_pipeline"
    assert operators[5].kwargs["conf"] == {
        "dataset": "train",
        "stage": "Production",
        "source_dag_id": "feature_pipeline",
        "source_run_id": "{{ run_id }}",
    }
    assert operators[5].kwargs["wait_for_completion"] is False


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
    ]
    assert operators[0].kwargs["op_kwargs"] == {
        "dataset": "validation",
        "run_key": "{{ run_id }}",
    }


def test_training_dag_stays_manual_and_paused_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, operators = _load_dag_module(monkeypatch, "dags/training_dag.py")

    assert module.dag.kwargs["schedule"] is None
    assert module.dag.kwargs["catchup"] is False
    assert module.dag.kwargs["is_paused_upon_creation"] is True
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
    assert operators[0].kwargs["op_kwargs"] == {"dataset": expected_dataset_template}
    assert operators[1].kwargs["op_kwargs"] == {"dataset": expected_dataset_template}
    assert operators[2].kwargs["op_kwargs"] == {"stage": expected_stage_template}


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
    assert operators[0].kwargs["op_kwargs"] == {"dataset": expected_dataset_template}
    assert operators[1].kwargs["op_kwargs"] == {"dataset": expected_dataset_template}
