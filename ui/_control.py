"""Client for the serving API's pipeline control-plane routes."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from foehncast.env import env_value

_SERVE_BASE_URL = (env_value("FOEHNCAST_SERVE_URL") or "http://127.0.0.1:8000").rstrip(
    "/"
)
_GET_TIMEOUT = 10
_TRIGGER_TIMEOUT = 20  # Airflow's dagRuns POST can take well over 10 s.


@dataclass(frozen=True)
class ControlRuns:
    """Recent pipeline runs, or the reason they are unavailable."""

    runs: list[dict[str, Any]]
    error: str | None = None


def _request(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    timeout: int = _GET_TIMEOUT,
) -> dict[str, Any]:
    url = f"{_SERVE_BASE_URL}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"}
    token = env_value("FOEHNCAST_CONTROL_TOKEN")
    if token:
        headers["X-Foehncast-Control-Token"] = token
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return json.load(resp)


def _error_detail(exc: urllib.error.HTTPError) -> str:
    try:
        detail = json.load(exc).get("detail")
    except Exception:
        detail = None
    return str(detail) if detail else f"HTTP {exc.code}"


def control_capabilities() -> list[str] | None:
    """Pipelines the active orchestrator can run, or None when unavailable."""
    try:
        data = _request("GET", "/pipeline/capabilities")
    except Exception:
        return None
    pipelines = data.get("pipelines")
    return list(pipelines) if pipelines else None


def control_runs(limit: int = 15) -> ControlRuns:
    """Recent runs across pipelines; error carries the failure reason."""
    try:
        data = _request("GET", f"/pipeline/runs?limit={limit}")
    except urllib.error.HTTPError as exc:
        return ControlRuns(runs=[], error=_error_detail(exc))
    except Exception:
        return ControlRuns(runs=[], error="serving API unreachable")
    return ControlRuns(runs=list(data.get("runs", [])))


def trigger_pipeline_run(pipeline: str) -> tuple[str | None, str | None]:
    """Trigger one pipeline; returns (run_id, error), one of them None."""
    try:
        data = _request(
            "POST",
            "/pipeline/run",
            payload={"pipeline": pipeline},
            timeout=_TRIGGER_TIMEOUT,
        )
    except urllib.error.HTTPError as exc:
        return None, _error_detail(exc)
    except Exception:
        return None, "serving API unreachable"
    return data.get("run_id"), None
