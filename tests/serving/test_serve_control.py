"""Tests for the pipeline control-plane routes in ``inference_pipeline.serve``."""

from __future__ import annotations

from dataclasses import asdict

import pytest
from fastapi.testclient import TestClient

from foehncast.inference_pipeline import serve
from foehncast.orchestration.control_plane import OrchestratorError, PipelineRun

RUN = PipelineRun(run_id="run-1", pipeline="feature", state="queued", started_at="T10")
TOKEN_HEADER = {"X-Foehncast-Control-Token": "sekret"}


class FakeOrchestrator:
    def __init__(
        self,
        runs: list[PipelineRun] | None = None,
        error: OrchestratorError | None = None,
    ) -> None:
        self._runs = runs or []
        self._error = error

    def capabilities(self) -> list[str]:
        return ["feature", "training", "inference"]

    def trigger(self, pipeline: str) -> PipelineRun:
        if self._error:
            raise self._error
        return RUN

    def list_runs(self, limit: int = 5) -> list[PipelineRun]:
        if self._error:
            raise self._error
        return self._runs[:limit]


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("FOEHNCAST_CONTROL_TOKEN", "sekret")
    return TestClient(serve.app)


def _use(
    monkeypatch: pytest.MonkeyPatch, orchestrator: FakeOrchestrator | None
) -> None:
    monkeypatch.setattr(serve, "build_orchestrator", lambda: orchestrator)


def test_capabilities_lists_pipelines(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use(monkeypatch, FakeOrchestrator())
    response = client.get("/pipeline/capabilities")
    assert response.status_code == 200
    assert response.json() == {"pipelines": ["feature", "training", "inference"]}


def test_capabilities_503_when_unconfigured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use(monkeypatch, None)
    assert client.get("/pipeline/capabilities").status_code == 503


def test_runs_serializes_runs_and_keeps_empty_distinct_from_unconfigured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use(monkeypatch, FakeOrchestrator(runs=[RUN]))
    response = client.get("/pipeline/runs")
    assert response.status_code == 200
    assert response.json() == {"runs": [asdict(RUN)]}

    _use(monkeypatch, FakeOrchestrator(runs=[]))
    assert client.get("/pipeline/runs").json() == {"runs": []}

    _use(monkeypatch, None)
    assert client.get("/pipeline/runs").status_code == 503


def test_runs_502_on_orchestrator_error(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use(monkeypatch, FakeOrchestrator(error=OrchestratorError("airflow down")))
    assert client.get("/pipeline/runs").status_code == 502


def test_run_rejects_missing_or_wrong_token(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use(monkeypatch, FakeOrchestrator())
    body = {"pipeline": "feature"}
    assert client.post("/pipeline/run", json=body).status_code == 401
    wrong = {"X-Foehncast-Control-Token": "nope"}
    assert client.post("/pipeline/run", json=body, headers=wrong).status_code == 401


def test_run_401_when_token_env_unset(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use(monkeypatch, FakeOrchestrator())
    monkeypatch.delenv("FOEHNCAST_CONTROL_TOKEN")
    response = client.post(
        "/pipeline/run", json={"pipeline": "feature"}, headers=TOKEN_HEADER
    )
    assert response.status_code == 401


def test_run_triggers_with_valid_token(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use(monkeypatch, FakeOrchestrator())
    response = client.post(
        "/pipeline/run", json={"pipeline": "feature"}, headers=TOKEN_HEADER
    )
    assert response.status_code == 202
    assert response.json() == asdict(RUN)


def test_run_400_unsupported_and_422_unknown_pipeline(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use(monkeypatch, FakeOrchestrator())
    response = client.post(
        "/pipeline/run", json={"pipeline": "cascade"}, headers=TOKEN_HEADER
    )
    assert response.status_code == 400
    response = client.post(
        "/pipeline/run", json={"pipeline": "bogus"}, headers=TOKEN_HEADER
    )
    assert response.status_code == 422


def test_run_503_unconfigured_with_valid_token(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use(monkeypatch, None)
    response = client.post(
        "/pipeline/run", json={"pipeline": "feature"}, headers=TOKEN_HEADER
    )
    assert response.status_code == 503
