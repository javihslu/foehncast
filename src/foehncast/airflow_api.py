"""Helpers for checking Airflow API payloads from shell entrypoints."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from foehncast._json import json_object_mapping
from foehncast.env import env_value


REQUIRED_AIRFLOW_HEALTH_COMPONENTS = (
    "metadatabase",
    "scheduler",
    "dag_processor",
    "triggerer",
)


def _payload_mapping(payload: Mapping[str, Any] | str | None) -> dict[str, Any]:
    return json_object_mapping(
        payload,
        error_message="Airflow API payload must decode to a JSON object.",
    )


def airflow_api_health_errors(payload: Mapping[str, Any] | str | None) -> list[str]:
    """Return unhealthy required component statuses from an Airflow health payload."""
    health_payload = _payload_mapping(payload)
    failures: list[str] = []

    for name in REQUIRED_AIRFLOW_HEALTH_COMPONENTS:
        status = (health_payload.get(name) or {}).get("status")
        if status != "healthy":
            failures.append(f"{name}={status!r}")

    return failures


def airflow_dag_run_status(
    payload: Mapping[str, Any] | str | None,
    *,
    expected_state: str,
    expected_run_id: str = "",
    expected_run_type: str = "",
) -> dict[str, Any]:
    """Classify the latest relevant Airflow DAG run state from a dagRuns payload."""
    dag_runs_payload = _payload_mapping(payload)
    runs = dag_runs_payload.get("dag_runs") or []

    if expected_run_id:
        runs = [run for run in runs if (run.get("dag_run_id") or "") == expected_run_id]
    elif expected_run_type:
        runs = [run for run in runs if (run.get("run_type") or "") == expected_run_type]

    if not runs:
        return {"status": "missing", "dag_run_id": "", "state": "", "run": None}

    run = runs[0]
    state = str(run.get("state") or "").lower()
    dag_run_id = str(run.get("dag_run_id") or "")

    if state == expected_state.lower():
        return {
            "status": "success",
            "dag_run_id": dag_run_id,
            "state": state,
            "run": run,
        }

    if state in {"failed", "error"}:
        return {
            "status": "failed",
            "dag_run_id": dag_run_id,
            "state": state,
            "run": run,
        }

    return {
        "status": "pending",
        "dag_run_id": dag_run_id,
        "state": state,
        "run": run,
    }


# Trigger client for the local Airflow 3 REST API. A short-lived bearer token is
# minted from the SimpleAuthManager /auth/token endpoint, then used to POST a
# manual dag run. All failures return a typed result; nothing raises to the UI.

_DEFAULT_AIRFLOW_URL = "http://localhost:8080"
_AUTH_TIMEOUT_SECONDS = 5
# The dagRuns POST serializes the DAG and schedules the run, so it runs a few
# seconds (matches the retired _gcp trigger timeout); auth is much quicker.
_TRIGGER_TIMEOUT_SECONDS = 15
# Listing runs is a plain read, so a shorter timeout keeps the UI responsive.
_READ_TIMEOUT_SECONDS = 8


@dataclass(frozen=True)
class AirflowTriggerResult:
    """Outcome of a DAG-trigger attempt; error is empty only when ok is True."""

    ok: bool
    dag_run_id: str = ""
    error: str = ""


def airflow_base_url() -> str:
    """Base URL of the Airflow API server, overridable via env."""
    return (env_value("FOEHNCAST_AIRFLOW_API_URL") or _DEFAULT_AIRFLOW_URL).rstrip("/")


def _airflow_credentials() -> tuple[str, str]:
    """Admin username/password for the SimpleAuthManager token exchange."""
    username = env_value("AIRFLOW_ADMIN_USERNAME") or "admin"
    password = env_value("AIRFLOW_ADMIN_PASSWORD") or "admin"
    return username, password


def build_token_request(
    base_url: str, username: str, password: str
) -> urllib.request.Request:
    """Build the POST /auth/token request that mints a bearer token."""
    body = json.dumps({"username": username, "password": password}).encode("utf-8")
    return urllib.request.Request(
        f"{base_url.rstrip('/')}/auth/token",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )


def build_dag_run_request(
    base_url: str,
    dag_id: str,
    token: str,
    *,
    conf: Mapping[str, Any] | None = None,
) -> urllib.request.Request:
    """Build the POST /api/v2/dags/{dag_id}/dagRuns request for a manual run."""
    body = json.dumps({"logical_date": None, "conf": dict(conf or {})}).encode("utf-8")
    return urllib.request.Request(
        f"{base_url.rstrip('/')}/api/v2/dags/{dag_id}/dagRuns",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )


def _read_json(request: urllib.request.Request, timeout: int) -> dict[str, Any]:
    """Send a prepared request and decode its JSON body."""
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def _fetch_token(base_url: str, username: str, password: str) -> str:
    payload = _read_json(
        build_token_request(base_url, username, password), _AUTH_TIMEOUT_SECONDS
    )
    token = str(payload.get("access_token") or "")
    if not token:
        raise ValueError("auth response missing access_token")
    return token


def _error_reason(exc: Exception) -> str:
    """Compact, UI-safe description of a transport failure."""
    if isinstance(exc, urllib.error.HTTPError):
        try:
            detail = exc.read().decode("utf-8").strip()[:200]
        except Exception:
            detail = ""
        return f"HTTP {exc.code}: {detail}" if detail else f"HTTP {exc.code}"
    if isinstance(exc, urllib.error.URLError):
        return f"unreachable: {exc.reason}"
    return str(exc) or exc.__class__.__name__


def airflow_triggers_available(base_url: str | None = None) -> bool:
    """True when the Airflow API server is reachable and accepts our credentials."""
    url = base_url or airflow_base_url()
    username, password = _airflow_credentials()
    try:
        return bool(_fetch_token(url, username, password))
    except (urllib.error.URLError, OSError, ValueError):
        return False


def trigger_dag(
    dag_id: str,
    *,
    base_url: str | None = None,
    conf: Mapping[str, Any] | None = None,
) -> AirflowTriggerResult:
    """Authenticate, then queue one manual run of dag_id. Never raises to callers."""
    url = base_url or airflow_base_url()
    username, password = _airflow_credentials()
    try:
        token = _fetch_token(url, username, password)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return AirflowTriggerResult(
            ok=False, error=f"auth failed ({_error_reason(exc)})"
        )
    try:
        payload = _read_json(
            build_dag_run_request(url, dag_id, token, conf=conf),
            _TRIGGER_TIMEOUT_SECONDS,
        )
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return AirflowTriggerResult(ok=False, error=_error_reason(exc))
    run_id = str(payload.get("dag_run_id") or "")
    if not run_id:
        return AirflowTriggerResult(
            ok=False, error="trigger response missing dag_run_id"
        )
    return AirflowTriggerResult(ok=True, dag_run_id=run_id)


# Read client for recent DAG-run history. Same bearer-token flow as trigger_dag,
# but a GET against the dagRuns collection ordered newest-first. All failures
# return a typed result with an empty run list; nothing raises to the UI.


@dataclass(frozen=True)
class AirflowDagRun:
    """One Airflow DAG run, trimmed to what the System tab renders."""

    dag_run_id: str
    state: str
    logical_date: str
    run_type: str
    run_after: str = ""


@dataclass(frozen=True)
class AirflowDagRunsResult:
    """Recent DAG runs plus an error string; error is empty only on success."""

    runs: list[AirflowDagRun]
    error: str = ""


def build_list_dag_runs_request(
    base_url: str, dag_id: str, token: str, *, limit: int = 5
) -> urllib.request.Request:
    """Build the GET /api/v2/dags/{dag_id}/dagRuns request, newest run first."""
    query = urllib.parse.urlencode({"limit": limit, "order_by": "-run_after"})
    return urllib.request.Request(
        f"{base_url.rstrip('/')}/api/v2/dags/{dag_id}/dagRuns?{query}",
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )


def _parse_dag_run(run: Mapping[str, Any]) -> AirflowDagRun:
    return AirflowDagRun(
        dag_run_id=str(run.get("dag_run_id") or ""),
        state=str(run.get("state") or "").lower(),
        logical_date=str(run.get("logical_date") or ""),
        run_type=str(run.get("run_type") or ""),
        run_after=str(run.get("run_after") or ""),
    )


def list_dag_runs(
    dag_id: str, limit: int = 5, base_url: str | None = None
) -> AirflowDagRunsResult:
    """Fetch the most recent runs of dag_id, newest first. Never raises to callers."""
    url = base_url or airflow_base_url()
    username, password = _airflow_credentials()
    try:
        token = _fetch_token(url, username, password)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return AirflowDagRunsResult(
            runs=[], error=f"auth failed ({_error_reason(exc)})"
        )
    try:
        payload = _read_json(
            build_list_dag_runs_request(url, dag_id, token, limit=limit),
            _READ_TIMEOUT_SECONDS,
        )
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return AirflowDagRunsResult(runs=[], error=_error_reason(exc))
    runs = [_parse_dag_run(run) for run in (payload.get("dag_runs") or [])]
    return AirflowDagRunsResult(runs=runs)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m foehncast.airflow_api")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("health")

    dag_run_parser = subparsers.add_parser("dag-run")
    dag_run_parser.add_argument("--expected-state", required=True)
    dag_run_parser.add_argument("--expected-run-id", default="")
    dag_run_parser.add_argument("--expected-run-type", default="")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    payload = sys.stdin.read()

    if args.command == "health":
        errors = airflow_api_health_errors(payload)
        if errors:
            print(", ".join(errors), file=sys.stderr)
            return 1
        return 0

    if args.command == "dag-run":
        result = airflow_dag_run_status(
            payload,
            expected_state=args.expected_state,
            expected_run_id=args.expected_run_id,
            expected_run_type=args.expected_run_type,
        )
        if result["status"] == "success":
            if result["dag_run_id"]:
                print(result["dag_run_id"])
            return 0
        if result["status"] == "failed":
            print(json.dumps(result["run"], sort_keys=True), file=sys.stderr)
            return 2
        return 1

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())
