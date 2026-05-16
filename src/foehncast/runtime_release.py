"""Helpers for normalizing and persisting runtime release handoff requests."""

from __future__ import annotations

from collections.abc import Sequence
import argparse
from collections.abc import Mapping
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import sys
from typing import Any

from foehncast._json import json_object_mapping, read_json_file, write_pretty_json
from foehncast._report_store import history_json_paths
from foehncast._time import compact_utc_timestamp
from foehncast.paths import project_root


ALLOWED_RUNTIME_RELEASE_ACTIONS = {
    "deploy_candidate",
    "promote_candidate",
    "rollback_live",
}
RUNTIME_RELEASE_REPORT_PATH_ENV = "FOEHNCAST_RUNTIME_RELEASE_REPORT_PATH"


def runtime_release_report_dir() -> Path:
    """Return the stable report directory for runtime release handoffs."""
    return project_root() / "airflow" / "reports"


def runtime_release_summary_path() -> Path:
    """Return the stable JSON summary path for the latest runtime release handoff."""
    return runtime_release_report_dir() / "runtime-release-latest.json"


def configured_runtime_release_summary_location() -> str:
    """Return the configured summary target for runtime release acknowledgements."""
    configured_location = os.environ.get(RUNTIME_RELEASE_REPORT_PATH_ENV, "").strip()
    return configured_location or str(runtime_release_summary_path())


def _is_gcs_location(location: str) -> bool:
    return location.startswith("gs://")


def _parse_gcs_location(location: str) -> tuple[str, str]:
    normalized_location = location.strip()
    bucket_name, separator, object_name = normalized_location[5:].partition("/")
    object_name = object_name.strip("/")
    if not bucket_name or not separator or not object_name:
        raise ValueError(
            "Runtime release GCS report path must look like "
            "'gs://bucket/path/to/runtime-release-latest.json'."
        )
    return bucket_name, object_name


def _new_storage_client() -> Any:
    from google.cloud import storage

    return storage.Client()


def _write_gcs_json_object(location: str, payload: dict[str, Any]) -> None:
    bucket_name, object_name = _parse_gcs_location(location)
    blob = _new_storage_client().bucket(bucket_name).blob(object_name)
    blob.upload_from_string(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        content_type="application/json",
    )


def _read_gcs_json_object(location: str, *, error_message: str) -> dict[str, Any]:
    bucket_name, object_name = _parse_gcs_location(location)
    blob = _new_storage_client().bucket(bucket_name).blob(object_name)
    if not blob.exists():
        raise FileNotFoundError(
            f"Runtime release report was not written to {location}."
        )

    payload = json.loads(blob.download_as_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(error_message)
    return payload


def _history_location(
    summary_location: str,
    *,
    prefix: str,
    payload: dict[str, Any],
    timestamp_field: str = "generated_at",
) -> str:
    filename = f"{prefix}-{compact_utc_timestamp(payload.get(timestamp_field))}.json"

    if _is_gcs_location(summary_location):
        bucket_name, object_name = _parse_gcs_location(summary_location)
        object_dir = object_name.rpartition("/")[0]
        history_name = "/".join(
            part for part in (object_dir, "history", filename) if part
        )
        return f"gs://{bucket_name}/{history_name}"

    return str(Path(summary_location).parent / "history" / filename)


def _gcs_history_prefix(summary_location: str, *, prefix: str) -> tuple[str, str]:
    bucket_name, object_name = _parse_gcs_location(summary_location)
    object_dir = object_name.rpartition("/")[0]
    history_prefix = "/".join(
        part for part in (object_dir, "history", f"{prefix}-") if part
    )
    return bucket_name, history_prefix


def runtime_release_summary_history_paths() -> list[str | Path]:
    """Return persisted runtime release handoff history paths or URIs."""
    summary_location = configured_runtime_release_summary_location()
    if _is_gcs_location(summary_location):
        bucket_name, history_prefix = _gcs_history_prefix(
            summary_location,
            prefix="runtime-release",
        )
        return [
            f"gs://{bucket_name}/{blob.name}"
            for blob in sorted(
                _new_storage_client().list_blobs(bucket_name, prefix=history_prefix),
                key=lambda item: item.name,
            )
            if blob.name.endswith(".json")
        ]

    return history_json_paths(
        Path(summary_location).parent,
        "runtime-release-*.json",
    )


def _write_runtime_release_history(
    summary: dict[str, Any],
    summary_location: str,
) -> str | Path:
    history_location = _history_location(
        summary_location,
        prefix="runtime-release",
        payload=summary,
    )
    _write_runtime_release_json(history_location, summary)
    if _is_gcs_location(history_location):
        return history_location
    return Path(history_location)


def _write_runtime_release_json(location: str, payload: dict[str, Any]) -> None:
    if _is_gcs_location(location):
        _write_gcs_json_object(location, payload)
        return

    write_pretty_json(Path(location), payload)


def _read_runtime_release_json(location: str) -> dict[str, Any]:
    if _is_gcs_location(location):
        return _read_gcs_json_object(
            location,
            error_message="Runtime release report must decode to a JSON object.",
        )

    path = Path(location)
    if not path.is_file():
        raise FileNotFoundError(
            f"Runtime release report was not written to {location}."
        )

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


def _normalized_airflow_target(value: Any, *, default: str = "") -> str:
    return _normalized_string(value, default=default).lower()


def _github_run_url_from_env(environ: Mapping[str, Any]) -> str:
    configured_url = _normalized_string(environ.get("GITHUB_RUN_URL"))
    if configured_url:
        return configured_url

    server_url = _normalized_string(environ.get("GITHUB_SERVER_URL")).rstrip("/")
    repository = _normalized_string(environ.get("GITHUB_REPOSITORY")).strip("/")
    run_id = _normalized_string(environ.get("GITHUB_RUN_ID"))
    if server_url and repository and run_id:
        return "/".join([server_url, repository, "actions", "runs", run_id])
    return ""


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
        "requested_airflow_target": _normalized_airflow_target(
            payload.get("requested_airflow_target"),
            default="unspecified",
        ),
        "selected_airflow_target": _normalized_airflow_target(
            payload.get("selected_airflow_target"),
            default="",
        ),
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

    if (
        not normalized_request["selected_airflow_target"]
        and normalized_request["requested_airflow_target"] == "composer_airflow"
    ):
        normalized_request["selected_airflow_target"] = normalized_request[
            "requested_airflow_target"
        ]

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


def runtime_release_request_from_env(
    environ: Mapping[str, Any] | None = None,
    *,
    requested_at: str | None = None,
) -> dict[str, str]:
    """Build a normalized runtime release request from workflow environment values."""
    env = os.environ if environ is None else environ
    return normalize_runtime_release_request(
        {
            "action": env.get("ACTION"),
            "request_source": env.get("REQUEST_SOURCE", "github-actions"),
            "requested_at": requested_at or datetime.now(tz=UTC).isoformat(),
            "github_repository": env.get("GITHUB_REPOSITORY"),
            "github_workflow": env.get("GITHUB_WORKFLOW"),
            "github_run_id": env.get("GITHUB_RUN_ID"),
            "github_run_url": _github_run_url_from_env(env),
            "github_sha": env.get("GITHUB_SHA"),
            "requested_airflow_target": env.get(
                "REQUESTED_AIRFLOW_TARGET",
                "unspecified",
            ),
            "selected_airflow_target": env.get("AIRFLOW_TARGET", ""),
            "image_uri": env.get("IMAGE_URI", ""),
            "candidate_revision_tag": env.get("CANDIDATE_REVISION_TAG", "candidate"),
            "candidate_alias": env.get("CANDIDATE_ALIAS", "candidate"),
            "target_alias": env.get("TARGET_ALIAS", "champion"),
            "rollback_revision": env.get("ROLLBACK_REVISION", ""),
            "rollback_model_version": env.get("ROLLBACK_MODEL_VERSION", ""),
            "rollback_revision_tag": env.get("ROLLBACK_REVISION_TAG", "rollback"),
        }
    )


def write_runtime_release_request_file(
    output_path: str | Path,
    *,
    environ: Mapping[str, Any] | None = None,
    requested_at: str | None = None,
) -> Path:
    """Persist a normalized runtime release request built from environment values."""
    output_file = Path(output_path)
    write_pretty_json(
        output_file,
        runtime_release_request_from_env(
            environ,
            requested_at=requested_at,
        ),
    )
    return output_file


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
        "requested_airflow_target": normalized_request["requested_airflow_target"],
        "selected_airflow_target": normalized_request["selected_airflow_target"],
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


def write_runtime_release_summary(summary: dict[str, Any]) -> Path | str:
    """Persist the latest runtime release handoff summary and a history copy."""
    summary_location = _resolved_runtime_release_summary_location()
    _write_runtime_release_json(summary_location, summary)
    _write_runtime_release_history(summary, summary_location)
    if _is_gcs_location(summary_location):
        return summary_location
    return Path(summary_location)


def _resolved_runtime_release_summary_location(
    report_path: str | Path | None = None,
) -> str:
    if report_path is None:
        return configured_runtime_release_summary_location()

    resolved_path = str(report_path).strip()
    return resolved_path or configured_runtime_release_summary_location()


def read_runtime_release_summary(
    report_path: str | Path | None = None,
) -> dict[str, Any]:
    """Read a persisted runtime release summary from disk."""
    summary_location = _resolved_runtime_release_summary_location(report_path)
    return _read_runtime_release_json(summary_location)


def verify_runtime_release_summary(
    expected_run_id: str,
    report_path: str | Path | None = None,
) -> dict[str, Any]:
    """Return the persisted runtime release summary after checking the DAG run id."""
    summary_location = _resolved_runtime_release_summary_location(report_path)
    summary = read_runtime_release_summary(summary_location)
    if summary.get("dag_run_id") != expected_run_id:
        raise ValueError(
            f"runtime release report does not match dag run {expected_run_id!r}"
        )
    summary["report_path"] = summary_location
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

    write_request_parser = subparsers.add_parser("write-request-from-env")
    write_request_parser.add_argument("--output-file", required=True)

    normalize_parser = subparsers.add_parser("normalize-request")
    normalize_parser.add_argument("--request-file", required=True)

    verify_parser = subparsers.add_parser("verify-report")
    verify_parser.add_argument("--expected-run-id", required=True)
    verify_parser.add_argument("--report-path", default="")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "write-request-from-env":
            print(write_runtime_release_request_file(args.output_file))
            return 0

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
    except (FileNotFoundError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())


__all__ = [
    "ALLOWED_RUNTIME_RELEASE_ACTIONS",
    "build_runtime_release_summary",
    "runtime_release_request_from_env",
    "normalize_runtime_release_request",
    "normalized_runtime_release_request_json",
    "read_runtime_release_summary",
    "record_runtime_release_request",
    "runtime_release_report_dir",
    "write_runtime_release_request_file",
    "runtime_release_summary_history_paths",
    "runtime_release_summary_path",
    "verify_runtime_release_summary",
    "write_runtime_release_summary",
]
