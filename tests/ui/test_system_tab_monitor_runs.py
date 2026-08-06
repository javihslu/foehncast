"""Tests for the System tab's monitor-run chip helper."""

from __future__ import annotations

import pathlib
import sys

_UI = pathlib.Path(__file__).resolve().parents[2] / "ui"
if str(_UI) not in sys.path:
    sys.path.insert(0, str(_UI))

from _system_tab import (  # noqa: E402
    _MONITOR_RUNS_WINDOW_EXPR,
    _monitor_runs_chip,
)


def test_window_expression_tolerates_counter_resets() -> None:
    assert _MONITOR_RUNS_WINDOW_EXPR == (
        "sum(increase(foehncast_prediction_monitoring_execution_total[24h]))"
    )


def test_chip_prefers_the_windowed_increase() -> None:
    assert _monitor_runs_chip(12.0, 3.0) == ("Monitor runs (24 h)", "12")


def test_chip_falls_back_to_the_process_total() -> None:
    assert _monitor_runs_chip(None, 3.0) == ("Monitor runs (since restart)", "3")


def test_chip_reports_missing_data() -> None:
    assert _monitor_runs_chip(None, None) == ("Monitor runs", "—")
