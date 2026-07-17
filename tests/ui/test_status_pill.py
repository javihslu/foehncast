"""The pipeline status pill reads an in-flight stage as running, not failed."""

from __future__ import annotations

import pathlib
import sys

# ui modules import each other by bare name, so ui/ must be on sys.path.
_UI = pathlib.Path(__file__).resolve().parents[2] / "ui"
if str(_UI) not in sys.path:
    sys.path.insert(0, str(_UI))

from _system_tab import _stage_is_running, _status_pill_html  # noqa: E402


def test_stage_is_running() -> None:
    assert _stage_is_running(0.0) is True
    assert _stage_is_running(1.0) is False  # done
    assert _stage_is_running(-1.0) is False  # failed
    assert _stage_is_running(float("nan")) is False


def test_status_pill_running_overrides_failed() -> None:
    # success=0 alone reads "failed", but an in-flight stage shows running.
    assert "running" in _status_pill_html(0.0, 1.0, running=True)
    assert "last run failed" in _status_pill_html(0.0, 1.0)
    assert "last run ok" in _status_pill_html(1.0, 1.0)
