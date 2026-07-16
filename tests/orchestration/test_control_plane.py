"""Tests for the pipeline control-plane adapters and the env factory."""

from __future__ import annotations

from typing import Any

import pytest

from foehncast.airflow_api import (
    AirflowDagRun,
    AirflowDagRunsResult,
    AirflowTriggerResult,
)
from foehncast.orchestration import control_plane as cp


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


def _workflows_request(method: str, url: str, **_: Any) -> _FakeResponse:
    if "metadata.google.internal" in url:
        return _FakeResponse({"access_token": "tok"})
    if method == "POST":
        return _FakeResponse({"name": "exec-1", "state": "ACTIVE"})
    return _FakeResponse(
        {"executions": [{"name": "exec-1", "state": "SUCCEEDED", "startTime": "T10"}]}
    )


def test_airflow_trigger_maps_run_and_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def _trigger(ok: bool, **kw: Any):
        return lambda dag_id, **_: AirflowTriggerResult(ok=ok, **kw)

    monkeypatch.setattr(cp, "trigger_dag", _trigger(True, dag_run_id="run-1"))
    orch = cp.AirflowOrchestrator()
    assert orch.capabilities() == ["feature", "training", "inference"]
    assert orch.trigger("feature") == cp.PipelineRun("run-1", "feature", "queued", "")
    with pytest.raises(cp.OrchestratorError):
        orch.trigger("unknown")

    monkeypatch.setattr(cp, "trigger_dag", _trigger(False, error="down"))
    with pytest.raises(cp.OrchestratorError):
        orch.trigger("feature")


def test_airflow_list_runs_merges_sorts_and_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    by_dag = {
        "feature_pipeline": [AirflowDagRun("f1", "success", "", "manual", "T09")],
        "training_pipeline": [AirflowDagRun("t1", "running", "", "manual", "T11")],
        "inference_pipeline": [],
    }
    monkeypatch.setattr(
        cp,
        "list_dag_runs",
        lambda dag_id, **_: AirflowDagRunsResult(runs=by_dag[dag_id]),
    )
    runs = cp.AirflowOrchestrator().list_runs(limit=5)
    assert [r.run_id for r in runs] == ["t1", "f1"]  # newest run_after first
    assert runs[0].pipeline == "training"
    assert runs[0].started_at == "T11"

    monkeypatch.setattr(
        cp,
        "list_dag_runs",
        lambda dag_id, **_: AirflowDagRunsResult(runs=[], error="x"),
    )
    with pytest.raises(cp.OrchestratorError):
        cp.AirflowOrchestrator().list_runs()


def test_workflows_trigger_list_and_capabilities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cp.httpx, "request", _workflows_request)
    orch = cp.WorkflowsOrchestrator(project="p", region="r", workflow_name="wf")
    assert orch.trigger("cascade") == cp.PipelineRun("exec-1", "cascade", "active", "")
    assert orch.capabilities() == ["cascade"]
    listed = orch.list_runs(limit=3)
    assert [r.run_id for r in listed] == ["exec-1"]
    assert listed[0].started_at == "T10"

    monkeypatch.setattr(cp.httpx, "request", lambda *a, **k: _FakeResponse({}))
    with pytest.raises(cp.OrchestratorError):
        orch.trigger("cascade")


def test_build_orchestrator_selects_by_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cp, "env_value", {"FOEHNCAST_AIRFLOW_API_URL": "url"}.get)
    assert isinstance(cp.build_orchestrator(), cp.AirflowOrchestrator)
    monkeypatch.setattr(
        cp, "env_value", {"GCP_PROJECT_ID": "p", "GCP_LOCATION": "r"}.get
    )
    assert isinstance(cp.build_orchestrator(), cp.WorkflowsOrchestrator)
    monkeypatch.setattr(cp, "env_value", {}.get)
    assert cp.build_orchestrator() is None
