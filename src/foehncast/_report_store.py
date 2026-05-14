"""Internal helpers for timestamped JSON report persistence."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from foehncast._json import read_json_file, write_pretty_json
from foehncast._time import compact_utc_timestamp


def report_history_dir(report_dir: Path) -> Path:
    return report_dir / "history"


def history_json_paths(report_dir: Path, pattern: str) -> list[Path]:
    return sorted(report_history_dir(report_dir).glob(pattern))


def write_json_object(path: Path, payload: dict[str, Any]) -> None:
    write_pretty_json(path, payload)


def read_json_object(path: Path, *, error_message: str) -> dict[str, Any]:
    payload = read_json_file(path)
    if not isinstance(payload, dict):
        raise ValueError(error_message)
    return payload


def write_history_copy(
    report_dir: Path,
    *,
    prefix: str,
    payload: dict[str, Any],
    timestamp_field: str = "generated_at",
) -> Path:
    history_path = (
        report_history_dir(report_dir)
        / f"{prefix}-{compact_utc_timestamp(payload.get(timestamp_field))}.json"
    )
    write_json_object(history_path, payload)
    return history_path
