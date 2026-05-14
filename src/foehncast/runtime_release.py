"""Helpers for normalizing and persisting runtime release handoff requests."""

from __future__ import annotations

from collections.abc import Sequence
import argparse
from collections.abc import Mapping
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from foehncast._json import json_object_mapping, read_json_file, write_pretty_json
from foehncast._time import compact_utc_timestamp
from foehncast.paths import project_root


ALLOWED_RUNTIME_RELEASE_ACTIONS = {
    "deploy_candidate",
    "promote_candidate",
    "rollback_live",
}


def runtime_release_report_dir() -> Path:
    """Return the stable report directory for runtime release handoffs."""
    return project_root() / "airflow" / "reports"


def runtime_release_summary_path() -> Path:
    """Return the stable JSON summary path for the latest runtime release handoff."""
    return runtime_release_report_dir() / "runtime-release-latest.json"


def runtime_release_summary_history_paths() -> list[Path]:
    """Return persisted runtime release handoff history paths."""
    return sorted(
        (runtime_release_report_dir() / "history").glob("runtime-release-*.json")
    )


def _write_runtime_release_history(summary: dict[str, Any]) -> Path:
    history_path = (
        runtime_release_report_dir()
        / "history"
        / f"runtime-release-{compact_utc_timestamp(summary.get('generated_at'))}.json"
    )
    _write_runtime_release_json(history_path, summary)
    return history_path


def _write_runtime_release_json(path: Path, payload: dict[str, Any]) -> None:
    write_pretty_json(path, payload)


def _read_runtime_release_json(path: Path) -> dict[str, Any]:
    payload = read_json_file(path)
    if not isinstance(payload, dict):
        raise ValueError("Runtime release report must decode to a JSON object.")
    return payload


def _request_mapping(request: Mapping[str, Any] | str | None) -> dict[str, Any]:
    return json_object_mapping(
        request,
        error_message="Runtime release request must decode to a JSON object.",
    )


def _normalized_string(value: Any, *, default: str = "") -> str:
    if value is None:
        return default
    normalized = str(value).strip()
    return normalized or default


def normalize_runtime_release_request(
    request: Mapping[str, Any] | str | None,
) -> dict[str, str]:
    """Normalize a runtime release request into the stable Airflow conf payload."""
    payload = _request_mapping(request)

    action = _normalized_string(payload.get("action")).lower()
    if action not in ALLOWED_RUNTIME_RELEASE_ACTIONS:
        raise ValueError(
            "Runtime release action must be one of deploy_candidate, "
            "promote_candidate, or rollback_live."
        )

    normalized_request = {
        "action": action,
        "request_source": _normalized_string(
            payload.get("request_source"),
            default="github-actions",
        ),
        "requested_at": _normalized_string(payload.get("requested_at")),
        "github_repository": _normalized_string(payload.get("github_repository")),
        "github_workflow": _normalized_string(payload.get("github_workflow")),
        "github_run_id": _normalized_string(payload.get("github_run_id")),
        "github_run_url": _normalized_string(payload.get("github_run_url")),
        "github_sha": _normalized_string(payload.get("github_sha")),
        "image_uri": _normalized_string(payload.get("image_uri")),
        "candidate_revision_tag": _normalized_string(
            payload.get("candidate_revision_tag"),
            default="candidate",
        ).lower(),
        "candidate_alias": _normalized_string(
            payload.get("candidate_alias"),
            default="candidate",
        ).lower(),
        "target_alias": _normalized_string(
            payload.get("target_alias"),
            default="champion",
        ).lower(),
        "rollback_revision": _normalized_string(payload.get("rollback_revision")),
        "rollback_model_version": _normalized_string(
            payload.get("rollback_model_version")
        ),
        "rollback_revision_tag": _normalized_string(
            payload.get("rollback_revision_tag"),
            default="rollback",
        ).lower(),
    }

    if not normalized_request["requested_at"]:
        normalized_request["requested_at"] = datetime.now(tz=UTC).isoformat()

    if action == "deploy_candidate" and not normalized_request["image_uri"]:
        raise ValueError("deploy_candidate requests require image_uri.")

    if action == "rollback_live":
        if not normalized_request["rollback_revision"]:
            raise ValueError("rollback_live requests require rollback_revision.")
        if not normalized_request["rollback_model_version"]:
            raise ValueError("rollback_live requests require rollback_model_version.")

    return normalized_request


def normalized_runtime_release_request_json(
    request: Mapping[str, Any] | str | None,
) -> str:
    """Return a normalized runtime release request as stable JSON."""
    return json.dumps(normalize_runtime_release_request(request), sort_keys=True)


def build_runtime_release_summary(
    request: Mapping[str, Any] | str | None,
    *,
    dag_run_id: str,
    dag_id: str = "runtime_release",
) -> dict[str, Any]:
    """Normalize a runtime release request into a stable observable summary."""
    normalized_request = normalize_runtime_release_request(request)

    return {
        "generated_at": normalized_request["requested_at"],
        "state": "accepted",
        "runtime_receiver": "hosted_airflow",
        "dag_id": dag_id,
        "dag_run_id": _normalized_string(dag_run_id, default="manual"),
        "action": normalized_request["action"],
        "request_source": normalized_request["request_source"],
        "github_repository": normalized_request["github_repository"],
        "github_workflow": normalized_request["github_workflow"],
        "github_run_id": normalized_request["github_run_id"],
        "github_run_url": normalized_request["github_run_url"],
        "github_sha": normalized_request["github_sha"],
        "image_uri": normalized_request["image_uri"],
        "candidate_revision_tag": normalized_request["candidate_revision_tag"],
        "candidate_alias": normalized_request["candidate_alias"],
        "target_alias": normalized_request["target_alias"],
        "rollback_revision": normalized_request["rollback_revision"],
        "rollback_model_version": normalized_request["rollback_model_version"],
        "rollback_revision_tag": normalized_request["rollback_revision_tag"],
    }


def write_runtime_release_summary(summary: dict[str, Any]) -> Path:
    """Persist the latest runtime release handoff summary and a history copy."""
    summary_path = runtime_release_summary_path()
    _write_runtime_release_json(summary_path, summary)
    _write_runtime_release_history(summary)
    return summary_path


def _resolved_runtime_release_summary_path(
    report_path: str | Path | None = None,
) -> Path:
    return (
        Path(report_path) if report_path is not None else runtime_release_summary_path()
    )


def read_runtime_release_summary(
    report_path: str | Path | None = None,
) -> dict[str, Any]:
    """Read a persisted runtime release summary from disk."""
    summary_path = _resolved_runtime_release_summary_path(report_path)
    if not summary_path.is_file():
        raise FileNotFoundError(
            f"Runtime release report was not written to {summary_path}."
        )

    return _read_runtime_release_json(summary_path)


def verify_runtime_release_summary(
    expected_run_id: str,
    report_path: str | Path | None = None,
) -> dict[str, Any]:
    """Return the persisted runtime release summary after checking the DAG run id."""
    summary_path = _resolved_runtime_release_summary_path(report_path)
    summary = read_runtime_release_summary(summary_path)
    if summary.get("dag_run_id") != expected_run_id:
        raise ValueError(
            f"runtime release report does not match dag run {expected_run_id!r}"
        )
    summary["report_path"] = str(summary_path)
    return summary


def record_runtime_release_request(
    request_json: Mapping[str, Any] | str | None = None,
    dag_run_id: str = "manual",
    dag_id: str = "runtime_release",
) -> str:
    """Normalize and persist the runtime release handoff request."""
    summary = build_runtime_release_summary(
        request_json,
        dag_run_id=dag_run_id,
        dag_id=dag_id,
    )
    return str(write_runtime_release_summary(summary))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m foehncast.runtime_release")
    subparsers = parser.add_subparsers(dest="command", required=True)

    normalize_parser = subparsers.add_parser("normalize-request")
    normalize_parser.add_argument("--request-file", required=True)

    verify_parser = subparsers.add_parser("verify-report")
    verify_parser.add_argument("--expected-run-id", required=True)
    verify_parser.add_argument("--report-path", default="")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "normalize-request":
        request_json = Path(args.request_file).read_text(encoding="utf-8")
        print(normalized_runtime_release_request_json(request_json))
        return 0

    if args.command == "verify-report":
        report_path = args.report_path or None
        print(
            json.dumps(
                verify_runtime_release_summary(
                    args.expected_run_id,
                    report_path=report_path,
                ),
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())


__all__ = [
    "ALLOWED_RUNTIME_RELEASE_ACTIONS",
    "build_runtime_release_summary",
    "normalize_runtime_release_request",
    "normalized_runtime_release_request_json",
    "read_runtime_release_summary",
    "record_runtime_release_request",
    "runtime_release_report_dir",
    "runtime_release_summary_history_paths",
    "runtime_release_summary_path",
    "verify_runtime_release_summary",
    "write_runtime_release_summary",
]
