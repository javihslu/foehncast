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
    airflow_module.DAG = FakeDAG
    operators_module = types.ModuleType("airflow.operators")
    python_module = types.ModuleType("airflow.operators.python")
    python_module.PythonOperator = FakePythonOperator

    monkeypatch.setitem(sys.modules, "airflow", airflow_module)
    monkeypatch.setitem(sys.modules, "airflow.operators", operators_module)
    monkeypatch.setitem(sys.modules, "airflow.operators.python", python_module)

    for name in (
        "AIRFLOW_FEATURE_DATASET",
        "AIRFLOW_FEATURE_SCHEDULE",
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
    assert len(operators) == 1
    assert operators[0].kwargs["task_id"] == "run_feature_pipeline"
    assert operators[0].kwargs["op_kwargs"] == {"dataset": "train"}


def test_feature_dag_supports_manual_override_and_dataset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, operators = _load_dag_module(
        monkeypatch,
        "dags/feature_dag.py",
        env={
            "AIRFLOW_FEATURE_DATASET": "validation",
            "AIRFLOW_FEATURE_SCHEDULE": "manual",
        },
    )

    assert module.dag.kwargs["schedule"] is None
    assert operators[0].kwargs["op_kwargs"] == {"dataset": "validation"}
