"""Tests for the rider console: heatmap grid tooltip columns and click-to-focus sync."""

from __future__ import annotations

import json
import pathlib
import sys
import types

import pandas as pd
import pytest

# The ui modules import each other by bare name (e.g. `from _wind_map import`),
# so ui/ must be on sys.path before importing the rider console.
_UI = pathlib.Path(__file__).resolve().parents[2] / "ui"
if str(_UI) not in sys.path:
    sys.path.insert(0, str(_UI))

import _rider_console as rc  # noqa: E402


def test_quality_ramp_matches_validated_hexes() -> None:
    # Levels 2-5 only: level 1 is fill-free (see _quality_legend_html), not
    # part of the color scale's range at all.
    assert rc._QUALITY_RAMP == ["#63b3a4", "#2f9384", "#0f7263", "#084c42"]


def test_all_spots_quality_grid_adds_tooltip_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    times = pd.date_range("2026-07-12T09:00:00Z", periods=3, freq="h")

    def fake_timeline(spot_id: str, *args: object, **kwargs: object) -> pd.DataFrame:
        rows = []
        for t in times:
            rows.append({"time": t, "elevation": "10m", "wind_speed": 22.0})
            rows.append({"time": t, "elevation": "gusts", "wind_speed": 30.0})
        return pd.DataFrame(rows)

    def fake_wind_frame(spot_id: str) -> pd.DataFrame:
        return pd.DataFrame({"wind_direction_10m": [200.0, 210.0, 220.0]}, index=times)

    monkeypatch.setattr(rc, "focus_spot_timeline", fake_timeline)
    monkeypatch.setattr(rc, "_spot_wind_frame", fake_wind_frame)

    predictions = [
        {
            "spot_id": "silvaplana",
            "forecast": [
                {"time": t.isoformat(), "quality_index": q}
                for t, q in zip(times, [4.2, 3.1, 1.5])
            ],
        }
    ]
    ranked = [
        {
            "spot_id": "silvaplana",
            "quality_label": "Firing",
            "quality_index": 4.2,
            "rideable_hours": 5,
            "drive_minutes": 90.0,
            "session_hours": 3.0,
            "ride_drive_ratio": 1.4,
            "score": 0.812,
        }
    ]

    grid = rc.all_spots_quality_grid(
        ("silvaplana",),
        json.dumps(predictions),
        "Europe/Zurich",
        json.dumps(ranked),
    )

    new_columns = ("header", "dial", "direction", "quality_label", "score")
    for col in new_columns:
        assert col in grid.columns
    assert grid["dial"].iloc[0].startswith("data:image/svg+xml;base64,")
    assert grid["header"].iloc[0].startswith("Silvaplana - ")


def test_sync_slider_to_heatmap_click_guards_repeat_cell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    times = pd.date_range("2026-07-12T09:00:00Z", periods=2, freq="h")
    # The click handler now clamps against the slider's prediction-window
    # option list (passed in), so the click's hour is always a valid option.
    options = list(times)

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

    rc._sync_slider_to_heatmap_click(times[0], "silvaplana", options)
    assert rc.st.session_state["rider_focus_spot"] == "silvaplana"
    assert rc.st.session_state["wind_map_hour"] == times[0]
    assert len(rerun_calls) == 1

    # Same cell clicked again: the guard must skip the write and the rerun.
    rc._sync_slider_to_heatmap_click(times[0], "silvaplana", options)
    assert len(rerun_calls) == 1

    # A different spot at the same hour is a real change and applies again.
    rc._sync_slider_to_heatmap_click(times[0], "sils", options)
    assert rc.st.session_state["rider_focus_spot"] == "sils"
    assert len(rerun_calls) == 2


def test_timeseries_x_domain_shared_endpoints() -> None:
    # Given a heat grid, both time-series charts pin one shared domain running
    # from 24 h before now to the grid's last hour (the heatmap's own right
    # edge), so all three axes read one clock (R5).
    times = pd.date_range("2026-07-12T07:00:00Z", periods=14, freq="h")
    grid = pd.DataFrame({"time": times, "time_end": times + pd.Timedelta(hours=1)})
    now = pd.Timestamp("2026-07-12T12:00:00Z")

    prediction_end = grid["time_end"].max()
    domain = rc._timeseries_x_domain(prediction_end, now)

    assert domain == [now - pd.Timedelta(hours=24), prediction_end]
    # Right edge equals the grid's last hour: the same value the heatmap's
    # pinned domain uses, so the charts and heatmap cannot diverge.
    assert domain[1] == grid["time_end"].max()
    # No grid -> no pinned domain; the charts fall back to their own extent.
    assert rc._timeseries_x_domain(None, now) is None


def test_timeseries_x_domain_edges_share_end_tz() -> None:
    # One clock: both domain edges must carry the prediction end's display
    # timezone, never a stray UTC left edge mixed with Europe/Zurich data (#51).
    tz = "Europe/Zurich"
    prediction_end = pd.Timestamp("2026-07-12T20:00:00", tz=tz)
    now = pd.Timestamp.now(tz=prediction_end.tz)

    domain = rc._timeseries_x_domain(prediction_end, now)

    assert domain is not None
    assert str(domain[0].tz) == tz
    assert str(domain[1].tz) == tz


def test_clamp_to_slider_option_snaps_stale_hour() -> None:
    # A stale session hour dropped by a data refresh must snap to a real option
    # so the wind-map select_slider never raises on an unknown value.
    options = list(pd.date_range("2026-07-12T07:00:00Z", periods=14, freq="h"))
    stale = pd.Timestamp("2026-07-11T23:00:00Z")  # before the current window

    snapped = rc._clamp_to_slider_option(stale, options)
    assert snapped in options
    assert snapped == options[0]  # nearest surviving option

    # An hour already in the options is returned unchanged (no drift).
    assert rc._clamp_to_slider_option(options[5], options) == options[5]
    # Empty options -> None (caller falls back to the wind-frame hours).
    assert rc._clamp_to_slider_option(stale, []) is None


def test_selected_heat_cell_resolves_nearest_row_for_clicked_spot() -> None:
    # Grid columns mirror what all_spots_quality_grid produces after the
    # console assigns the display-name "spot" column (spot, time).
    times = pd.date_range(
        "2026-07-12T09:00:00", periods=3, freq="h", tz="Europe/Zurich"
    )
    grid = pd.DataFrame(
        {
            "spot": ["Silvaplana"] * 3 + ["Sils"] * 3,
            "time": list(times) + list(times),
        }
    )
    # Streamlit projects the click as epoch ms; ten minutes off still resolves
    # to the nearest row, not its hourly neighbors.
    click_ms = int(times[1].tz_convert("UTC").timestamp() * 1000) + 10 * 60 * 1000
    event = types.SimpleNamespace(
        selection={"cell": [{"spot": "Silvaplana", "time": click_ms}]}
    )

    row = rc._selected_heat_cell(event, grid)

    assert row is not None
    assert row["spot"] == "Silvaplana"
    assert row["time"] == times[1]


def test_selected_heat_cell_unknown_spot_returns_none() -> None:
    times = pd.date_range(
        "2026-07-12T09:00:00", periods=2, freq="h", tz="Europe/Zurich"
    )
    grid = pd.DataFrame({"spot": ["Silvaplana"] * 2, "time": list(times)})
    click_ms = int(times[0].tz_convert("UTC").timestamp() * 1000)
    event = types.SimpleNamespace(
        selection={"cell": [{"spot": "not-a-spot", "time": click_ms}]}
    )

    assert rc._selected_heat_cell(event, grid) is None


def test_selected_heat_cell_empty_selection_returns_none() -> None:
    times = pd.date_range(
        "2026-07-12T09:00:00", periods=2, freq="h", tz="Europe/Zurich"
    )
    grid = pd.DataFrame({"spot": ["Silvaplana"] * 2, "time": list(times)})

    assert rc._selected_heat_cell(types.SimpleNamespace(selection={}), grid) is None
    assert (
        rc._selected_heat_cell(types.SimpleNamespace(selection={"cell": []}), grid)
        is None
    )
    # No "selection" attribute at all -> getattr falls back to None.
    assert rc._selected_heat_cell(types.SimpleNamespace(), grid) is None


def test_minimum_rideable_kts_uses_light_threshold_below_weight_cutoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = {
        "minimum_wind_speed_10m": {
            "light_rider_max_weight_kg": 65.0,
            "light_rider_min_kts": 12.0,
            "default_min_kts": 16.0,
        }
    }
    monkeypatch.setattr(rc, "get_labeling_config", lambda: cfg)

    monkeypatch.setattr(rc, "get_rider_config", lambda: {"weight_kg": 60.0})
    assert rc._minimum_rideable_kts() == 12.0

    # At the weight cutoff itself the light threshold still applies (<=).
    monkeypatch.setattr(rc, "get_rider_config", lambda: {"weight_kg": 65.0})
    assert rc._minimum_rideable_kts() == 12.0

    monkeypatch.setattr(rc, "get_rider_config", lambda: {"weight_kg": 90.0})
    assert rc._minimum_rideable_kts() == 16.0


def test_night_bands_wraps_night_intervals_as_dataframe() -> None:
    lat, lon = 46.45, 9.79
    t_min = pd.Timestamp("2026-07-12T00:00:00", tz="Europe/Zurich")
    t_max = t_min + pd.Timedelta(hours=48)

    bands = rc._night_bands(t_min, t_max, lat, lon)
    expected = rc.night_intervals(lat, lon, t_min, t_max)

    assert list(bands.columns) == ["x", "x2"]
    assert len(bands) == len(expected)
    assert len(bands) >= 1
    for (_, row), (lo, hi) in zip(bands.iterrows(), expected, strict=True):
        assert row["x"] == lo
        assert row["x2"] == hi
        assert row["x"] < row["x2"]


def test_heatmap_tick_count_scales_with_window() -> None:
    start = pd.Timestamp("2026-07-12T00:00:00", tz="Europe/Zurich")
    # The live ~14 h serving horizon reads on a 2 h rhythm; the old constant 9
    # was one density for every window.
    assert rc._heatmap_tick_count(start, start + pd.Timedelta(hours=14)) == 8
    # A 48 h window keeps the original 6 h rhythm (9 ticks).
    assert rc._heatmap_tick_count(start, start + pd.Timedelta(hours=48)) == 9
    # Multi-day boards thin out to 12 h spacing.
    assert rc._heatmap_tick_count(start, start + pd.Timedelta(days=7)) == 15
    # Degenerate windows still hint at least two ticks.
    assert rc._heatmap_tick_count(start, start + pd.Timedelta(minutes=30)) == 2


def test_heatmap_x_axis_uses_numeric_tick_count() -> None:
    # The {"interval": ...} tickCount form crashes the bundled Vega on the
    # layered, domain-pinned heatmap, so the hint must stay a plain number.
    start = pd.Timestamp("2026-07-12T00:00:00", tz="Europe/Zurich")
    axis = rc._heatmap_x_axis(start, start + pd.Timedelta(days=7))
    assert isinstance(axis.tickCount, int)


def test_flat_week_detects_all_level_one_grid() -> None:
    assert rc._flat_week(pd.DataFrame({"quality": [1, 1, 1]}))
    assert not rc._flat_week(pd.DataFrame({"quality": [1, 3, 1]}))
    # An empty grid is "no data", not a quiet week: the chip must not show.
    assert not rc._flat_week(pd.DataFrame({"quality": []}))


def test_flat_week_chip_names_the_quiet_state() -> None:
    assert "Quiet week" in rc._FLAT_WEEK_CHIP


def test_quality_legend_html_has_one_chip_per_ramp_step() -> None:
    html = rc._quality_legend_html()

    assert "Session quality (1-5)" in html
    # Level 1 is the outline-only swatch (no ramp fill).
    assert (
        "border:1px solid rgba(7, 37, 42, 0.4);margin:0 0.3rem 0 0.9rem;"
        'vertical-align:-0.05rem"></span>1' in html
    )
    # Levels 2-5 each carry their ramp color as the chip background.
    for level, color in zip((2, 3, 4, 5), rc._QUALITY_RAMP, strict=True):
        assert (
            f"background:{color};margin:0 0.3rem 0 0.9rem;"
            f'vertical-align:-0.05rem"></span>{level}'
        ) in html
