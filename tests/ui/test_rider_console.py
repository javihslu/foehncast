"""Test for the heatmap-click-to-focus sync helper."""

from __future__ import annotations

import pathlib
import sys

import pandas as pd
import pytest

# The ui modules import each other by bare name (e.g. `from _wind_map import`),
# so ui/ must be on sys.path before importing the rider console.
_UI = pathlib.Path(__file__).resolve().parents[2] / "ui"
if str(_UI) not in sys.path:
    sys.path.insert(0, str(_UI))

import _rider_console as rc  # noqa: E402


def test_sync_slider_to_heatmap_click_guards_repeat_cell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    times = pd.date_range("2026-07-12T09:00:00Z", periods=2, freq="h")

    def fake_wind_frame(spot_id: str) -> pd.DataFrame:
        return pd.DataFrame({"wind_direction_10m": [200.0, 210.0]}, index=times)

    monkeypatch.setattr(rc, "_spot_wind_frame", fake_wind_frame)

    rerun_calls: list[dict[str, object]] = []
    monkeypatch.setattr(rc.st, "rerun", lambda **kw: rerun_calls.append(kw))
    for key in (
        "heat_hour_applied",
        "heat_spot_applied",
        "wind_map_hour",
        "wind_map_hour_seen",
        "rider_focus_spot",
    ):
        rc.st.session_state.pop(key, None)

    rc._sync_slider_to_heatmap_click(times[0], "silvaplana", ["silvaplana"])
    assert rc.st.session_state["rider_focus_spot"] == "silvaplana"
    assert rc.st.session_state["wind_map_hour"] == times[0]
    assert len(rerun_calls) == 1

    # Same cell clicked again: the guard must skip the write and the rerun.
    rc._sync_slider_to_heatmap_click(times[0], "silvaplana", ["silvaplana"])
    assert len(rerun_calls) == 1

    # A different spot at the same hour is a real change and applies again.
    rc._sync_slider_to_heatmap_click(times[0], "sils", ["silvaplana"])
    assert rc.st.session_state["rider_focus_spot"] == "sils"
    assert len(rerun_calls) == 2
