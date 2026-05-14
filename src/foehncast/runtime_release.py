"""Helpers for normalizing and persisting runtime release handoff requests."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

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


def _summary_history_timestamp(generated_at: str | None) -> str:
    timestamp = datetime.now(tz=UTC)
    if generated_at:
        try:
            timestamp = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        except ValueError:
            timestamp = datetime.now(tz=UTC)

    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    else:
        timestamp = timestamp.astimezone(UTC)

    return timestamp.strftime("%Y%m%dT%H%M%S%fZ")


def _write_runtime_release_history(summary: dict[str, Any]) -> Path:
    history_path = (
        runtime_release_report_dir()
        / "history"
        / f"runtime-release-{_summary_history_timestamp(summary.get('generated_at'))}.json"
    )
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return history_path


def _request_mapping(request: Mapping[str, Any] | str | None) -> dict[str, Any]:
    if request is None:
        return {}

    if isinstance(request, Mapping):
        return dict(request)

    request_json = str(request).strip()
    if not request_json:
        return {}

    payload = json.loads(request_json)
    if not isinstance(payload, dict):
        raise ValueError("Runtime release request must decode to a JSON object.")
    return payload


def _normalized_string(value: Any, *, default: str = "") -> str:
    if value is None:
        return default
    normalized = str(value).strip()
    return normalized or default


def build_runtime_release_summary(
    request: Mapping[str, Any] | str | None,
    *,
    dag_run_id: str,
    dag_id: str = "runtime_release",
) -> dict[str, Any]:
    """Normalize a runtime release request into a stable observable summary."""
    payload = _request_mapping(request)

    action = _normalized_string(payload.get("action")).lower()
    if action not in ALLOWED_RUNTIME_RELEASE_ACTIONS:
        raise ValueError(
            "Runtime release action must be one of deploy_candidate, "
            "promote_candidate, or rollback_live."
        )

    image_uri = _normalized_string(payload.get("image_uri"))
    candidate_revision_tag = _normalized_string(
        payload.get("candidate_revision_tag"),
        default="candidate",
    ).lower()
    candidate_alias = _normalized_string(
        payload.get("candidate_alias"),
        default="candidate",
    ).lower()
    target_alias = _normalized_string(
        payload.get("target_alias"),
        default="champion",
    ).lower()
    rollback_revision = _normalized_string(payload.get("rollback_revision"))
    rollback_model_version = _normalized_string(payload.get("rollback_model_version"))
    rollback_revision_tag = _normalized_string(
        payload.get("rollback_revision_tag"),
        default="rollback",
    ).lower()

    if action == "deploy_candidate" and not image_uri:
        raise ValueError("deploy_candidate requests require image_uri.")

    if action == "rollback_live":
        if not rollback_revision:
            raise ValueError("rollback_live requests require rollback_revision.")
        if not rollback_model_version:
            raise ValueError("rollback_live requests require rollback_model_version.")

    generated_at = _normalized_string(payload.get("requested_at"))
    if not generated_at:
        generated_at = datetime.now(tz=UTC).isoformat()

    return {
        "generated_at": generated_at,
        "state": "accepted",
        "runtime_receiver": "hosted_airflow",
        "dag_id": dag_id,
        "dag_run_id": _normalized_string(dag_run_id, default="manual"),
        "action": action,
        "request_source": _normalized_string(
            payload.get("request_source"),
            default="github-actions",
        ),
        "github_repository": _normalized_string(payload.get("github_repository")),
        "github_workflow": _normalized_string(payload.get("github_workflow")),
        "github_run_id": _normalized_string(payload.get("github_run_id")),
        "github_run_url": _normalized_string(payload.get("github_run_url")),
        "github_sha": _normalized_string(payload.get("github_sha")),
        "image_uri": image_uri,
        "candidate_revision_tag": candidate_revision_tag,
        "candidate_alias": candidate_alias,
        "target_alias": target_alias,
        "rollback_revision": rollback_revision,
        "rollback_model_version": rollback_model_version,
        "rollback_revision_tag": rollback_revision_tag,
    }


def write_runtime_release_summary(summary: dict[str, Any]) -> Path:
    """Persist the latest runtime release handoff summary and a history copy."""
    summary_path = runtime_release_summary_path()
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    _write_runtime_release_history(summary)
    return summary_path


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


__all__ = [
    "ALLOWED_RUNTIME_RELEASE_ACTIONS",
    "build_runtime_release_summary",
    "record_runtime_release_request",
    "runtime_release_report_dir",
    "runtime_release_summary_history_paths",
    "runtime_release_summary_path",
    "write_runtime_release_summary",
]
