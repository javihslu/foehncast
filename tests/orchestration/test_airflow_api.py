"""Tests for shell-facing Airflow API helpers."""

from __future__ import annotations

import io
import json

import pytest

import foehncast.airflow_api as airflow_api


def test_airflow_api_health_errors_lists_unhealthy_required_components() -> None:
    errors = airflow_api.airflow_api_health_errors(
        {
            "metadatabase": {"status": "healthy"},
            "scheduler": {"status": "healthy"},
            "dag_processor": {"status": "starting"},
            "triggerer": {"status": "unhealthy"},
        }
    )

    assert errors == ["dag_processor='starting'", "triggerer='unhealthy'"]


def test_airflow_api_health_errors_rejects_non_object_json_payload() -> None:
    with pytest.raises(
        ValueError,
        match="Airflow API payload must decode to a JSON object.",
    ):
        airflow_api.airflow_api_health_errors('["not-an-object"]')


def test_airflow_dag_run_status_filters_by_run_type() -> None:
    result = airflow_api.airflow_dag_run_status(
        {
            "dag_runs": [
                {"dag_run_id": "manual__1", "run_type": "manual", "state": "queued"},
                {
                    "dag_run_id": "asset__1",
                    "run_type": "asset_triggered",
                    "state": "success",
                },
            ]
        },
        expected_state="success",
        expected_run_type="asset_triggered",
    )

    assert result["status"] == "success"
    assert result["dag_run_id"] == "asset__1"


def test_airflow_dag_run_status_reports_terminal_failure() -> None:
    result = airflow_api.airflow_dag_run_status(
        {
            "dag_runs": [
                {
                    "dag_run_id": "runtime_release__1",
                    "state": "failed",
                    "run_type": "manual",
                }
            ]
        },
        expected_state="success",
        expected_run_id="runtime_release__1",
    )

    assert result["status"] == "failed"
    assert result["state"] == "failed"
    assert result["run"]["dag_run_id"] == "runtime_release__1"


# CLI entrypoint (main)


def test_main_health_returns_0_for_healthy_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = (
        '{"metadatabase":{"status":"healthy"},"scheduler":{"status":"healthy"},'
        '"dag_processor":{"status":"healthy"},"triggerer":{"status":"healthy"}}'
    )
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(payload))
    assert airflow_api.main(["health"]) == 0


def test_main_health_returns_1_for_unhealthy_payload(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = (
        '{"metadatabase":{"status":"healthy"},"scheduler":{"status":"unhealthy"},'
        '"dag_processor":{"status":"healthy"},"triggerer":{"status":"healthy"}}'
    )
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(payload))
    assert airflow_api.main(["health"]) == 1
    assert "scheduler" in capsys.readouterr().err


def test_main_dag_run_returns_0_and_prints_run_id_on_success(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = (
        '{"dag_runs":[{"dag_run_id":"run_1","state":"success","run_type":"manual"}]}'
    )
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(payload))
    assert airflow_api.main(["dag-run", "--expected-state", "success"]) == 0
    assert "run_1" in capsys.readouterr().out


def test_main_dag_run_returns_2_and_prints_run_on_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = (
        '{"dag_runs":[{"dag_run_id":"run_2","state":"failed","run_type":"manual"}]}'
    )
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(payload))
    assert airflow_api.main(["dag-run", "--expected-state", "success"]) == 2
    assert "run_2" in capsys.readouterr().err


def test_main_dag_run_returns_1_when_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = (
        '{"dag_runs":[{"dag_run_id":"run_3","state":"running","run_type":"manual"}]}'
    )
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(payload))
    assert airflow_api.main(["dag-run", "--expected-state", "success"]) == 1


# Trigger client (mocked transport, no network)


class _FakeResponse:
    """Minimal urlopen stand-in that returns a fixed JSON body."""

    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


def _transport(token_payload: dict, run_payload: dict, captured: list):
    """Fake urlopen: /auth/token returns the token, everything else the run."""

    def _urlopen(request, timeout=None):
        captured.append(request)
        if request.full_url.endswith("/auth/token"):
            return _FakeResponse(token_payload)
        return _FakeResponse(run_payload)

    return _urlopen


def test_build_token_request_posts_credentials_to_auth_endpoint() -> None:
    request = airflow_api.build_token_request("http://airflow:8080/", "admin", "s3cret")

    assert request.full_url == "http://airflow:8080/auth/token"
    assert request.get_method() == "POST"
    assert request.get_header("Content-type") == "application/json"
    assert json.loads(request.data) == {"username": "admin", "password": "s3cret"}


def test_build_dag_run_request_sets_bearer_and_targets_v2_endpoint() -> None:
    request = airflow_api.build_dag_run_request(
        "http://airflow:8080", "runtime_release", "tok-xyz", conf={"note": "hi"}
    )

    assert request.full_url == "http://airflow:8080/api/v2/dags/runtime_release/dagRuns"
    assert request.get_method() == "POST"
    assert request.get_header("Authorization") == "Bearer tok-xyz"
    body = json.loads(request.data)
    assert body["conf"] == {"note": "hi"}
    assert body["logical_date"] is None


def test_trigger_dag_returns_run_id_with_bearer_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list = []
    monkeypatch.setattr(
        airflow_api.urllib.request,
        "urlopen",
        _transport({"access_token": "tok-123"}, {"dag_run_id": "manual__x"}, captured),
    )

    result = airflow_api.trigger_dag("runtime_release", base_url="http://airflow:8080")

    assert result.ok is True
    assert result.dag_run_id == "manual__x"
    # Second request is the dag-run POST; it must carry the minted bearer token.
    assert captured[1].get_header("Authorization") == "Bearer tok-123"
    assert captured[1].full_url.endswith("/api/v2/dags/runtime_release/dagRuns")


def test_trigger_dag_returns_clean_error_when_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(request, timeout=None):
        raise airflow_api.urllib.error.URLError("connection refused")

    monkeypatch.setattr(airflow_api.urllib.request, "urlopen", _boom)

    result = airflow_api.trigger_dag("runtime_release", base_url="http://airflow:8080")

    assert result.ok is False
    assert "auth failed" in result.error


def test_trigger_dag_returns_error_with_response_body_snippet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(request, timeout=None):
        if request.full_url.endswith("/auth/token"):
            return _FakeResponse({"access_token": "tok-123"})
        body = json.dumps({"detail": "DAG runtime_release is paused"}).encode("utf-8")
        raise airflow_api.urllib.error.HTTPError(
            request.full_url, 409, "Conflict", {}, io.BytesIO(body)
        )

    monkeypatch.setattr(airflow_api.urllib.request, "urlopen", _boom)

    result = airflow_api.trigger_dag("runtime_release", base_url="http://airflow:8080")

    assert result.ok is False
    assert result.error.startswith("HTTP 409:")
    assert "DAG runtime_release is paused" in result.error


# Read client (mocked transport, no network)


def test_build_list_dag_runs_request_sets_bearer_and_query_params() -> None:
    request = airflow_api.build_list_dag_runs_request(
        "http://airflow:8080", "feature_pipeline", "tok-xyz", limit=5
    )

    assert request.get_method() == "GET"
    assert request.full_url.startswith(
        "http://airflow:8080/api/v2/dags/feature_pipeline/dagRuns?"
    )
    assert "limit=5" in request.full_url
    assert "order_by=-run_after" in request.full_url
    assert request.get_header("Authorization") == "Bearer tok-xyz"


def test_list_dag_runs_returns_typed_runs_with_bearer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list = []
    run_payload = {
        "dag_runs": [
            {
                "dag_run_id": "scheduled__1",
                "state": "SUCCESS",
                "run_type": "scheduled",
                "logical_date": "2026-07-11T18:00:00Z",
                "run_after": "2026-07-11T18:00:00Z",
            }
        ]
    }
    monkeypatch.setattr(
        airflow_api.urllib.request,
        "urlopen",
        _transport({"access_token": "tok-123"}, run_payload, captured),
    )

    result = airflow_api.list_dag_runs(
        "feature_pipeline", base_url="http://airflow:8080"
    )

    assert result.error == ""
    assert len(result.runs) == 1
    run = result.runs[0]
    assert run.dag_run_id == "scheduled__1"
    assert run.state == "success"  # normalized to lower-case
    assert run.run_type == "scheduled"
    # Second request is the dagRuns GET; it must carry the minted bearer token.
    assert captured[1].get_method() == "GET"
    assert captured[1].get_header("Authorization") == "Bearer tok-123"
    assert "order_by=-run_after" in captured[1].full_url


def test_list_dag_runs_returns_empty_list_when_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(request, timeout=None):
        raise airflow_api.urllib.error.URLError("connection refused")

    monkeypatch.setattr(airflow_api.urllib.request, "urlopen", _boom)

    result = airflow_api.list_dag_runs(
        "feature_pipeline", base_url="http://airflow:8080"
    )

    assert result.runs == []
    assert "auth failed" in result.error
