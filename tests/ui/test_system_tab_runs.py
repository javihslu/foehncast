"""Tests for the System tab's control-plane run rendering helpers."""

from __future__ import annotations

import pathlib
import sys

import pytest

_UI = pathlib.Path(__file__).resolve().parents[2] / "ui"
if str(_UI) not in sys.path:
    sys.path.insert(0, str(_UI))

import _system_tab  # noqa: E402
from _system_tab import _group_runs, _run_age, _run_row_html  # noqa: E402


def test_run_age_parses_iso_and_handles_missing() -> None:
    assert _run_age({"started_at": ""}) == "—"
    assert _run_age({"started_at": "not-a-date"}) == "—"
    assert _run_age({"started_at": "2026-07-16T22:19:58Z"}).endswith("ago")


def test_run_row_html_uses_state_and_short_id() -> None:
    row = _run_row_html(
        {
            "run_id": "projects/p/locations/l/executions/exec-1",
            "pipeline": "cascade",
            "state": "succeeded",
            "started_at": "",
        }
    )
    assert "succeeded" in row and "exec-1" in row and "projects/p" not in row


def test_group_runs_by_pipeline_preserves_order() -> None:
    runs = [
        {"run_id": "a", "pipeline": "feature"},
        {"run_id": "b", "pipeline": "cascade"},
        {"run_id": "c", "pipeline": "feature"},
    ]
    grouped = _group_runs(runs)
    assert [r["run_id"] for r in grouped["feature"]] == ["a", "c"]
    assert [r["run_id"] for r in grouped["cascade"]] == ["b"]


def test_render_recent_runs_distinguishes_unavailable_from_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captions: list[str] = []
    markdowns: list[str] = []
    monkeypatch.setattr(_system_tab.st, "caption", lambda msg: captions.append(msg))
    monkeypatch.setattr(
        _system_tab.st, "markdown", lambda html, **kw: markdowns.append(html)
    )

    _system_tab._render_recent_runs(None)  # unavailable: renders nothing itself
    assert captions == []
    assert markdowns == []

    _system_tab._render_recent_runs([])  # empty: its own distinct caption
    assert captions == ["No recent runs recorded."]
    assert markdowns == []
