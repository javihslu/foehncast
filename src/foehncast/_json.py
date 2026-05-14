"""Private JSON helpers for shell-facing contracts and local persistence."""

from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path
from typing import Any


def write_pretty_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def read_json_file(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_json_file_if_exists(path: Path) -> Any | None:
    if not path.exists():
        return None
    return read_json_file(path)


def json_object_mapping(
    payload: Mapping[str, Any] | str | None,
    *,
    error_message: str,
) -> dict[str, Any]:
    if payload is None:
        return {}

    if isinstance(payload, Mapping):
        return dict(payload)

    payload_json = str(payload).strip()
    if not payload_json:
        return {}

    parsed = json.loads(payload_json)
    if not isinstance(parsed, dict):
        raise ValueError(error_message)
    return parsed