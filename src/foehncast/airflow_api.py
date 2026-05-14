"""Helpers for checking Airflow API payloads from shell entrypoints."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import argparse
import json
import sys
from typing import Any

from foehncast._json import json_object_mapping


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