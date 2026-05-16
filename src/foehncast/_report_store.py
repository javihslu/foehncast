"""Internal helpers for timestamped JSON report persistence."""

from __future__ import annotations

import fnmatch
import json
from pathlib import Path
from typing import Any

from foehncast._json import read_json_file, write_pretty_json
from foehncast._time import compact_utc_timestamp

ReportLocation = str | Path


def _normalized_report_location(location: ReportLocation) -> str:
    return str(location).strip()


def _is_gcs_location(location: ReportLocation) -> bool:
    return _normalized_report_location(location).startswith("gs://")


def _parse_gcs_location(location: ReportLocation) -> tuple[str, str]:
    normalized_location = _normalized_report_location(location)
    bucket_name, _, object_name = normalized_location[5:].partition("/")
    if not bucket_name:
        raise ValueError("GCS report path must include a bucket name.")
    return bucket_name, object_name.strip("/")


def _new_storage_client() -> Any:
    from google.cloud import storage

    return storage.Client()


def _gcs_prefix(object_name: str) -> str:
    if not object_name:
        return ""
    return f"{object_name.rstrip('/')}/"


def report_object_path(report_dir: ReportLocation, filename: str) -> ReportLocation:
    if _is_gcs_location(report_dir):
        return f"{_normalized_report_location(report_dir).rstrip('/')}/{filename}"
    return Path(report_dir) / filename


def report_history_dir(report_dir: ReportLocation) -> ReportLocation:
    if _is_gcs_location(report_dir):
        return f"{_normalized_report_location(report_dir).rstrip('/')}/history"
    return Path(report_dir) / "history"


def report_json_paths(report_dir: ReportLocation, pattern: str) -> list[ReportLocation]:
    if _is_gcs_location(report_dir):
        bucket_name, object_name = _parse_gcs_location(report_dir)
        prefix = _gcs_prefix(object_name)
        return [
            f"gs://{bucket_name}/{blob.name}"
            for blob in sorted(
                _new_storage_client().list_blobs(bucket_name, prefix=prefix),
                key=lambda item: item.name,
            )
            if "/" not in blob.name.removeprefix(prefix)
            and fnmatch.fnmatch(blob.name.rsplit("/", 1)[-1], pattern)
        ]

    return sorted(Path(report_dir).glob(pattern))


def history_json_paths(
    report_dir: ReportLocation, pattern: str
) -> list[ReportLocation]:
    if _is_gcs_location(report_dir):
        bucket_name, object_name = _parse_gcs_location(report_history_dir(report_dir))
        prefix = _gcs_prefix(object_name)
        return [
            f"gs://{bucket_name}/{blob.name}"
            for blob in sorted(
                _new_storage_client().list_blobs(bucket_name, prefix=prefix),
                key=lambda item: item.name,
            )
            if fnmatch.fnmatch(blob.name.rsplit("/", 1)[-1], pattern)
        ]

    return sorted(report_history_dir(report_dir).glob(pattern))


def write_json_object(path: ReportLocation, payload: dict[str, Any]) -> None:
    if _is_gcs_location(path):
        bucket_name, object_name = _parse_gcs_location(path)
        if not object_name:
            raise ValueError("GCS report path must include an object name.")

        _new_storage_client().bucket(bucket_name).blob(object_name).upload_from_string(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            content_type="application/json",
        )
        return

    write_pretty_json(Path(path), payload)


def read_json_object(path: ReportLocation, *, error_message: str) -> dict[str, Any]:
    if _is_gcs_location(path):
        bucket_name, object_name = _parse_gcs_location(path)
        if not object_name:
            raise ValueError("GCS report path must include an object name.")

        blob = _new_storage_client().bucket(bucket_name).blob(object_name)
        if not blob.exists():
            raise FileNotFoundError(f"Report was not written to {path}.")

        payload = json.loads(blob.download_as_text(encoding="utf-8"))
    else:
        payload = read_json_file(Path(path))

    if not isinstance(payload, dict):
        raise ValueError(error_message)
    return payload


def write_history_copy(
    report_dir: ReportLocation,
    *,
    prefix: str,
    payload: dict[str, Any],
    timestamp_field: str = "generated_at",
) -> ReportLocation:
    history_path = report_object_path(
        report_history_dir(report_dir),
        f"{prefix}-{compact_utc_timestamp(payload.get(timestamp_field))}.json",
    )
    write_json_object(history_path, payload)
    return history_path
