"""Tests for shared timestamped JSON report persistence helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from foehncast import _report_store


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text())


def test_write_history_copy_writes_timestamped_history_file(tmp_path: Path) -> None:
    history_path = _report_store.write_history_copy(
        tmp_path,
        prefix="runtime-release",
        payload={
            "generated_at": "2026-05-14T11:00:00+00:00",
            "state": "accepted",
        },
    )

    assert (
        history_path
        == tmp_path / "history" / "runtime-release-20260514T110000000000Z.json"
    )
    assert _read_json(history_path)["state"] == "accepted"


def test_read_json_object_rejects_non_object_payload(tmp_path: Path) -> None:
    payload_path = tmp_path / "invalid.json"
    payload_path.write_text('["not-an-object"]\n', encoding="utf-8")

    with pytest.raises(ValueError, match="must decode to a JSON object"):
        _report_store.read_json_object(
            payload_path,
            error_message="Payload must decode to a JSON object.",
        )
