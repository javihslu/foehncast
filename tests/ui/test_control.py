"""Tests for the serve control-plane client used by the UI."""

from __future__ import annotations

import io
import json
import pathlib
import sys
import urllib.error

import pytest

_UI = pathlib.Path(__file__).resolve().parents[2] / "ui"
if str(_UI) not in sys.path:
    sys.path.insert(0, str(_UI))

import _control  # noqa: E402


class _Response(io.BytesIO):
    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: object) -> bool:
        return False


def _fake_urlopen(payload: dict, captured: list | None = None):
    def opener(req, timeout=0):
        if captured is not None:
            captured.append(req)
        return _Response(json.dumps(payload).encode())

    return opener


def _http_error(code: int, detail: str) -> urllib.error.HTTPError:
    body = io.BytesIO(json.dumps({"detail": detail}).encode())
    return urllib.error.HTTPError("url", code, "err", hdrs=None, fp=body)


def test_capabilities_parses_pipelines(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        _control.urllib.request, "urlopen", _fake_urlopen({"pipelines": ["feature"]})
    )
    assert _control.control_capabilities() == ["feature"]


def test_capabilities_none_when_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    def opener(req, timeout=0):
        raise urllib.error.URLError("down")

    monkeypatch.setattr(_control.urllib.request, "urlopen", opener)
    assert _control.control_capabilities() is None


def test_runs_ok_and_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    run = {"run_id": "r1", "pipeline": "feature", "state": "queued", "started_at": ""}
    monkeypatch.setattr(
        _control.urllib.request, "urlopen", _fake_urlopen({"runs": [run]})
    )
    result = _control.control_runs()
    assert result.runs == [run] and result.error is None

    monkeypatch.setattr(_control.urllib.request, "urlopen", _fake_urlopen({"runs": []}))
    result = _control.control_runs()
    assert result.runs == [] and result.error is None


def test_runs_maps_503_detail_to_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def opener(req, timeout=0):
        raise _http_error(503, "No pipeline orchestrator is configured")

    monkeypatch.setattr(_control.urllib.request, "urlopen", opener)
    result = _control.control_runs()
    assert result.runs == []
    assert "orchestrator" in (result.error or "")


def test_trigger_returns_run_id_and_sends_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list = []
    monkeypatch.setenv("FOEHNCAST_CONTROL_TOKEN", "tok")
    monkeypatch.setattr(
        _control.urllib.request,
        "urlopen",
        _fake_urlopen({"run_id": "run-9", "state": "queued"}, captured),
    )
    run_id, error = _control.trigger_pipeline_run("feature")
    assert run_id == "run-9" and error is None
    assert captured[0].get_header("X-foehncast-control-token") == "tok"


def test_trigger_maps_401_to_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def opener(req, timeout=0):
        raise _http_error(401, "Missing or invalid control token")

    monkeypatch.setattr(_control.urllib.request, "urlopen", opener)
    run_id, error = _control.trigger_pipeline_run("feature")
    assert run_id is None
    assert "token" in (error or "")
