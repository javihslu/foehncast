"""Tests for the rider console: heatmap grid tooltip columns and click-to-focus sync."""

from __future__ import annotations

import json
import pathlib
import sys
import types

import altair as alt
import pandas as pd
import pytest

# The ui modules import each other by bare name (e.g. `from _wind_map import`),
# so ui/ must be on sys.path before importing the rider console.
_UI = pathlib.Path(__file__).resolve().parents[2] / "ui"
if str(_UI) not in sys.path:
    sys.path.insert(0, str(_UI))

import _rider_console as rc  # noqa: E402
from _theme import DARK, LIGHT  # noqa: E402


def test_quality_ramp_matches_validated_hexes() -> None:
    # Levels 2-5 only: level 1 is fill-free (see _quality_legend_html), not
    # part of the color scale's range at all.
    assert LIGHT.quality == ("#63b3a4", "#2f9384", "#0f7263", "#084c42")
    # Dark is its own validated set, not a flip of the light one.
    assert DARK.quality == ("#276553", "#21826a", "#2b9e81", "#3dbb9a")


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
        False,
    )

    new_columns = ("header", "dial", "direction", "quality_label", "hour_quality")
    for col in new_columns:
        assert col in grid.columns
    assert grid["dial"].iloc[0].startswith("data:image/svg+xml;base64,")
    assert grid["header"].iloc[0].startswith("Silvaplana - ")
    # The spot's ranking score is constant across the row, so it cannot
    # describe an hour and must not ride on the cells.
    assert "score" not in grid.columns


def test_each_cell_carries_its_own_hourly_quality(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The hourly tooltip figure has to vary by hour, or it is claiming too much."""
    times = pd.date_range("2026-07-12T09:00:00Z", periods=3, freq="h")
    monkeypatch.setattr(rc, "focus_spot_timeline", lambda *a, **k: pd.DataFrame())
    monkeypatch.setattr(rc, "_spot_wind_frame", lambda *a, **k: pd.DataFrame())

    hourly_quality = [4.2, 3.1, 1.5]
    predictions = [
        {
            "spot_id": "silvaplana",
            "forecast": [
                {"time": t.isoformat(), "quality_index": q}
                for t, q in zip(times, hourly_quality)
            ],
        }
    ]
    ranked = [
        {"spot_id": "silvaplana", "quality_label": "Firing", "quality_index": 4.2}
    ]

    grid = rc.all_spots_quality_grid(
        ("silvaplana",),
        json.dumps(predictions),
        "Europe/Zurich",
        json.dumps(ranked),
        False,
    )

    assert grid["hour_quality"].tolist() == hourly_quality
    # The spot-level peak is the same on every cell; the hourly figure must not
    # be a copy of it, which is exactly what the old "Score" field was.
    assert grid["quality_index"].nunique() == 1
    assert grid["hour_quality"].nunique() == 3


def test_night_hours_never_render_as_a_quality_level(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No cell may carry a ramp level while the sun is below the horizon.

    The grid used to bucket every forecast hour, so a windy 02:00 painted the
    same green as a rideable afternoon.
    """
    monkeypatch.setattr(rc, "focus_spot_timeline", lambda *a, **k: pd.DataFrame())
    monkeypatch.setattr(rc, "_spot_wind_frame", lambda *a, **k: pd.DataFrame())

    # A full day, so the window straddles sunrise and sunset, and a quality that
    # would otherwise bucket to the top of the ramp on every single hour.
    times = pd.date_range("2026-01-15T00:00:00Z", periods=24, freq="h")
    predictions = [
        {
            "spot_id": "silvaplana",
            "forecast": [{"time": t.isoformat(), "quality_index": 4.6} for t in times],
        }
    ]
    grid = rc.all_spots_quality_grid(
        ("silvaplana",),
        json.dumps(predictions),
        "Europe/Zurich",
        json.dumps([{"spot_id": "silvaplana"}]),
        False,
    )

    spot = next(s for s in rc.get_spots() if s["id"] == "silvaplana")
    # Cells are judged at their midpoint (is_daylight_hour), so a cell counts
    # as night when the sun is down at H+30 -- the same rule the wind plot's
    # hourly night wash uses.
    mid = pd.DatetimeIndex(grid["time"]) + pd.Timedelta(minutes=30)
    elevation = rc.solar_elevation_deg(
        float(spot["lat"]), float(spot["lon"]), mid
    ).to_numpy()
    dark = elevation <= -0.833
    is_day = grid["is_day"].to_numpy()

    # The window has to contain both, or the assertions below prove nothing.
    assert dark.any() and (~dark).any()
    assert not is_day[dark].any()
    assert is_day[~dark].all()


def test_dangerous_hours_are_flagged_from_the_wind_not_the_level(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Too much wind has to be readable, and the quality level cannot say it.

    quality_bucket sends any index <= 0.5 to class 0, so the danger class and a
    dead-calm hour share a number. The cell reads the wind against the same
    ceilings the labeling model uses instead.
    """
    times = pd.date_range("2026-07-15T09:00:00Z", periods=3, freq="h")
    max_speed_kn, max_gust_kn = rc.dangerous_kts()
    # One hour over the speed ceiling, one over the gust ceiling, one ordinary.
    winds_kmh = [(max_speed_kn + 10) * 1.852, 20.0 * 1.852, 18.0 * 1.852]
    gusts_kmh = [(max_speed_kn + 15) * 1.852, (max_gust_kn + 5) * 1.852, 24.0 * 1.852]

    def fake_timeline(spot_id: str, *args: object, **kwargs: object) -> pd.DataFrame:
        rows = []
        for t, w, g in zip(times, winds_kmh, gusts_kmh, strict=True):
            rows.append({"time": t, "elevation": "10m", "wind_speed": w})
            rows.append({"time": t, "elevation": "gusts", "wind_speed": g})
        return pd.DataFrame(rows)

    monkeypatch.setattr(rc, "focus_spot_timeline", fake_timeline)
    monkeypatch.setattr(rc, "_spot_wind_frame", lambda *a, **k: pd.DataFrame())

    predictions = [
        {
            "spot_id": "silvaplana",
            "forecast": [{"time": t.isoformat(), "quality_index": 4.6} for t in times],
        }
    ]
    grid = rc.all_spots_quality_grid.__wrapped__(
        ("silvaplana",),
        json.dumps(predictions),
        "Europe/Zurich",
        json.dumps([{"spot_id": "silvaplana"}]),
        False,
    ).sort_values("time")

    assert grid["is_dangerous"].tolist() == [True, True, False]
    # The word carries it, so the fact does not rest on the cell's colour.
    assert grid["safety"].tolist()[2] == "Within the safe limits"
    assert "Too strong" in grid["safety"].tolist()[0]
    # The level itself is unchanged: it still floors at 1, which is precisely
    # why the flag has to exist.
    assert grid["quality"].min() >= 1


def test_dangerous_cell_bubble_does_not_say_too_light() -> None:
    # The floored level reads "1/5 (Too Light)" on an hour that is unrideable
    # for the opposite reason. The bubble takes its word from the wind.
    bubble = rc._selection_bubble_html(
        "Silvaplana", "Mon 04 Aug 14:00", 1, 90.0, 110.0, 200.0, True, True
    )
    assert "Too Light" not in bubble
    assert "Too strong" in bubble
    assert "Over the safe limit" in bubble


def test_dangerous_hour_still_reads_as_dangerous_on_the_rendered_cell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The danger class has to survive from the wind reading to the drawn cell.

    Two steps in between can erase it: the level floors at 1, and night cells
    leave the quality ramp for a single flat fill.
    """
    times = pd.date_range("2026-01-15T00:00:00Z", periods=24, freq="h")
    max_speed_kn, max_gust_kn = rc.dangerous_kts()
    # Too windy at 02:00 UTC (dark) and at 13:00 UTC (daylight), ordinary
    # otherwise, so the flag has to track the wind rather than the hour.
    windy = {2, 13}

    def fake_timeline(spot_id: str, *args: object, **kwargs: object) -> pd.DataFrame:
        rows = []
        for i, t in enumerate(times):
            over = i in windy
            speed = (max_speed_kn + 10 if over else 18.0) * 1.852
            gust = (max_gust_kn + 10 if over else 24.0) * 1.852
            rows.append({"time": t, "elevation": "10m", "wind_speed": speed})
            rows.append({"time": t, "elevation": "gusts", "wind_speed": gust})
        return pd.DataFrame(rows)

    monkeypatch.setattr(rc, "focus_spot_timeline", fake_timeline)
    monkeypatch.setattr(rc, "_spot_wind_frame", lambda *a, **k: pd.DataFrame())

    predictions = [
        {
            "spot_id": "silvaplana",
            "forecast": [{"time": t.isoformat(), "quality_index": 4.6} for t in times],
        }
    ]
    grid = rc.all_spots_quality_grid.__wrapped__(
        ("silvaplana",),
        json.dumps(predictions),
        "Europe/Zurich",
        json.dumps([{"spot_id": "silvaplana"}]),
        False,
    ).sort_values("time")

    dangerous = grid[grid["is_dangerous"]]
    assert len(dangerous) == len(windy)
    # One of the two is a night hour: the night handling must not take it back.
    assert set(dangerous["is_day"]) == {True, False}
    # Nothing else on those cells says it. The level sits in the rideable band,
    # and the night one is painted the same fill a dead-calm 02:00 gets.
    assert dangerous["quality"].between(1, 5).all()

    grid = grid.assign(spot="Silvaplana", t_ms=rc._epoch_ms(grid["time"]))
    chart, _ = rc._time_panel(
        grid,
        ["Silvaplana"],
        pd.DataFrame(),
        fake_timeline("silvaplana"),
        46.45,
        9.79,
        [grid["time"].min(), grid["time"].max() + pd.Timedelta(hours=1)],
        grid["time"].iloc[0],
        None,
        16.0,
    )
    board = chart.to_dict()["vconcat"][1]
    marks = [
        i
        for i, layer in enumerate(board["layer"])
        if {"filter": "datum.is_dangerous"} in layer.get("transform", [])
    ]
    assert len(marks) == 1
    danger_layer = board["layer"][marks[0]]
    # Above the quality cells, so neither the ramp nor the night fill paints
    # over it, and in its own colour rather than a step on the ramp.
    assert marks[0] > 0
    pal = rc.active()
    assert danger_layer["encoding"]["color"]["value"] == pal.danger
    assert pal.danger not in pal.quality and pal.danger != pal.night_fill


def test_quality_fill_keeps_night_off_the_ramp() -> None:
    """The fill encoding routes night to the off-ramp fill, day to the ramp.

    The ramp itself is continuous on the hour's own quality, anchored so the
    level-1 end fades to the bare surface, and clamped so an out-of-range
    index can never produce an undefined fill (the flat-week bug).
    """
    chart = (
        alt.Chart(pd.DataFrame({"is_day": [True], "hour_quality": [3.0]}))
        .mark_rect()
        .encode(color=rc._quality_fill(LIGHT))
    )
    enc = chart.to_dict()["encoding"]["color"]

    assert enc["value"] == LIGHT.night_fill
    condition = enc["condition"]
    assert condition["test"] == "datum.is_day"
    assert condition["field"] == "hour_quality"
    scale = condition["scale"]
    assert scale["domain"] == [1, 2, 3, 4, 5]
    assert scale["range"][1:] == list(LIGHT.quality)
    # The level-1 anchor is the first step at zero alpha: a fade, not a fill.
    assert scale["range"][0].startswith("rgba(")
    assert scale["range"][0].endswith(", 0.0)")
    assert scale["clamp"] is True


def test_night_is_labelled_not_just_colored() -> None:
    # Contrast vs the page surface is only 1.5:1, so the state must also be
    # carried in words: a legend chip and the selection bubble's own row.
    assert LIGHT.night_fill not in LIGHT.quality
    legend = rc._quality_legend_html()
    assert "Night" in legend
    assert LIGHT.night_fill in legend
    bubble = rc._selection_bubble_html(
        "Silvaplana", "Thu 15 Jan 02:00", 5, None, None, None, False
    )
    assert "Night" in bubble


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

    # A click on empty panel space carries no spot: it moves the pinned time
    # and leaves the focused spot alone.
    rc._sync_slider_to_heatmap_click(times[1], None, options)
    assert rc.st.session_state["wind_map_hour"] == times[1]
    assert rc.st.session_state["rider_focus_spot"] == "sils"
    assert len(rerun_calls) == 3
    # Same hour again, still no spot: nothing changed, so nothing reruns.
    rc._sync_slider_to_heatmap_click(times[1], None, options)
    assert len(rerun_calls) == 3


def test_panel_x_domain_is_the_grid_extent() -> None:
    # Every view in the panel shares one domain, and it is the heat grid's own
    # extent: its cells are rects, so reaching further back would compress them.
    tz = "Europe/Zurich"
    times = pd.date_range("2026-07-12T07:00:00", periods=14, freq="h", tz=tz)
    grid = pd.DataFrame({"time": times, "time_end": times + pd.Timedelta(hours=1)})
    timeline = pd.DataFrame({"time": times[2:6]})

    domain = rc._panel_x_domain(grid, timeline)

    assert domain == [times[0], times[-1] + pd.Timedelta(hours=1)]
    # One clock: both edges carry the display timezone, never a stray UTC edge
    # mixed with Europe/Zurich data (#51).
    assert str(domain[0].tz) == tz and str(domain[1].tz) == tz
    # No grid -> the wind timeline's own extent stands in, so the plot keeps a
    # clock instead of vanishing.
    assert rc._panel_x_domain(pd.DataFrame(), timeline) == [times[2], times[5]]
    # Neither -> no panel at all.
    assert rc._panel_x_domain(pd.DataFrame(), pd.DataFrame()) is None


def test_time_spine_covers_every_hour_with_epoch_ids() -> None:
    # The spine is the panel's shared hit target: one row per hour, each row
    # carrying the epoch milliseconds the hover and click params match on.
    start = pd.Timestamp("2026-07-12T06:00:00", tz="Europe/Zurich")
    spine = rc._time_spine(start, start + pd.Timedelta(hours=5))

    assert len(spine) == 5
    assert spine["time"].iloc[0] == start
    assert (spine["time_end"] - spine["time"] == pd.Timedelta(hours=1)).all()
    assert spine["t_ms"].iloc[0] == int(start.timestamp() * 1000)
    assert spine["t_ms"].is_monotonic_increasing


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


def test_night_bands_align_to_hourly_daylight_cells() -> None:
    lat, lon = 46.45, 9.79
    t_min = pd.Timestamp("2026-07-12T00:00:00", tz="Europe/Zurich")
    t_max = t_min + pd.Timedelta(hours=48)

    bands = rc._night_bands(t_min, t_max, lat, lon)
    hours = pd.date_range(t_min, t_max, freq="h", inclusive="left")
    day = rc.is_daylight_hour(lat, lon, hours)

    assert list(bands.columns) == ["x", "x2"]
    assert len(bands) >= 1
    covered: set[pd.Timestamp] = set()
    for _, row in bands.iterrows():
        assert row["x"] < row["x2"]
        # Edges sit on cell boundaries, where the heatmap's night cells sit.
        assert row["x"] == row["x"].floor("h")
        assert row["x2"] == row["x2"].floor("h")
        covered.update(
            pd.date_range(row["x"], row["x2"] - pd.Timedelta(hours=1), freq="h")
        )
    # The wash covers exactly the hours the heatmap rule calls night.
    assert {h for h in hours if not day[h]} == covered


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


def test_ruler_axis_uses_numeric_tick_count() -> None:
    # The {"interval": ...} tickCount form crashes the bundled Vega on the
    # layered, domain-pinned panel, so the hint must stay a plain number.
    start = pd.Timestamp("2026-07-12T00:00:00", tz="Europe/Zurich")
    axis = rc._ruler_axis("top", start, start + pd.Timedelta(days=7))
    assert isinstance(axis.tickCount, int)
    assert axis.orient == "top"
    # Ticks and labels only: the ruler is a measuring edge, not a grid.
    assert axis.grid is False
    assert axis.tickSize == 5


def test_flat_week_detects_all_level_one_grid() -> None:
    day = [True, True, True]
    assert rc._flat_week(pd.DataFrame({"quality": [1, 1, 1], "is_day": day}))
    assert not rc._flat_week(pd.DataFrame({"quality": [1, 3, 1], "is_day": day}))
    # An empty grid is "no data", not a quiet week: the chip must not show.
    assert not rc._flat_week(pd.DataFrame({"quality": [], "is_day": []}))
    # A strong night hour is not a session, so it must not clear the chip.
    assert rc._flat_week(
        pd.DataFrame({"quality": [1, 5, 1], "is_day": [True, False, True]})
    )


def test_flat_week_chip_names_the_quiet_state() -> None:
    assert "Quiet week" in rc._FLAT_WEEK_CHIP


def test_selection_wind_matches_nearest_hour(monkeypatch: pytest.MonkeyPatch) -> None:
    times = pd.date_range("2026-07-12T09:00:00Z", periods=3, freq="h")
    frame = pd.DataFrame(
        {
            "wind_speed_10m": [10.0, 20.0, 30.0],
            "wind_gusts_10m": [15.0, 25.0, 35.0],
            "wind_direction_10m": [180.0, 200.0, 220.0],
        },
        index=times,
    )
    monkeypatch.setattr(rc, "_spot_wind_frame", lambda sid: frame)

    near = pd.Series(
        {"spot_id": "silvaplana", "time": times[1] + pd.Timedelta(minutes=10)}
    )
    assert rc._selection_wind(near) == (20.0, 25.0, 200.0)

    # A pick more than 90 minutes from any frame hour yields no data.
    far = pd.Series(
        {"spot_id": "silvaplana", "time": times[-1] + pd.Timedelta(hours=4)}
    )
    assert rc._selection_wind(far) == (None, None, None)


def test_selection_bubble_html_carries_panel_fields() -> None:
    html = rc._selection_bubble_html(
        "Silvaplana", "Fri 17 Jul 09:00", 4, 22.0, 30.0, 200.0
    )
    assert "Silvaplana" in html and "Fri 17 Jul 09:00" in html
    assert "4/5" in html and "22 km/h" in html and "30 km/h" in html
    assert "border-radius:14px" in html

    # Missing wind drops those rows but keeps the card and quality line.
    bare = rc._selection_bubble_html("Sils", "Fri 17 Jul 09:00", 1, None, None, None)
    assert "Wind" not in bare and "1/5" in bare


_PANEL_SPOTS = ["Silvaplana", "Sils"]


def _panel_frames() -> tuple[
    pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DatetimeIndex
]:
    """Synthetic heat grid, wind timeline and accuracy marks for panel tests."""
    hours = pd.date_range(
        "2026-07-12T06:00:00", periods=12, freq="h", tz="Europe/Zurich"
    )
    rows = [
        {
            "spot": spot,
            "spot_id": spot.lower(),
            "time": t,
            "time_end": t + pd.Timedelta(hours=1),
            "quality": 3,
            "hour_quality": 3.0,
            "is_day": True,
            "daylight": "Day",
            "header": f"{spot} - {t:%a %H:00}",
            "dial": "",
            "wind": 20.0,
            "gust": 28.0,
            "direction": "SW (220)",
            "quality_label": "Firing",
            "quality_index": 4.2,
            "rideable_hours": 5,
            "drive_minutes": 90.0,
            "session_hours": 3.0,
            "ride_drive_ratio": 1.4,
        }
        for spot in _PANEL_SPOTS
        for t in hours
    ]
    grid = pd.DataFrame(rows)
    grid["t_ms"] = rc._epoch_ms(grid["time"])
    timeline = pd.DataFrame(
        [
            {"time": t, "elevation": e, "wind_speed": 20.0}
            for e in ("10m", "gusts")
            for t in hours
        ]
    )
    accuracy = pd.DataFrame(
        {
            "spot": _PANEL_SPOTS,
            "time": [hours[1], hours[2]],
            "predicted": [3.0, 3.0],
            "observed": [3.1, 4.6],
            "delta": [0.1, 1.6],
            "verdict": ["matched", "missed"],
        }
    )
    return grid, timeline, accuracy, hours


def _build_panel(
    pinned: pd.Timestamp | None, focus_spot: str | None = None
) -> tuple[dict, list[str]]:
    grid, timeline, accuracy, hours = _panel_frames()
    domain = [hours[0], hours[-1] + pd.Timedelta(hours=1)]
    chart, modes = rc._time_panel(
        grid,
        _PANEL_SPOTS,
        accuracy,
        timeline,
        46.45,
        9.79,
        domain,
        hours[3],
        pinned,
        16.0,
        focus_spot=focus_spot,
    )
    return chart.to_dict(), modes


def _x_channels(node: object) -> list[dict]:
    """Every x encoding in a view spec, layers included."""
    found: list[dict] = []
    if isinstance(node, dict):
        encoding = node.get("encoding", {})
        if "x" in encoding:
            found.append(encoding["x"])
        for child in node.get("layer", []):
            found.extend(_x_channels(child))
    return found


def test_time_panel_is_one_composite_on_one_domain() -> None:
    """Board and wind plot share a domain exactly, and only the rulers carry an axis."""
    hours = _panel_frames()[3]
    spec, _ = _build_panel(hours[4])

    views = spec["vconcat"]
    assert len(views) == 4  # top ruler, board, wind, bottom ruler
    # Views are laid out flush at one width, which is what makes the two plots
    # line up column for column.
    assert spec["bounds"] == "flush"
    assert {v["width"] for v in views} == {rc._PANEL_PLOT_WIDTH}

    domains = {str(x["scale"]["domain"]) for view in views for x in _x_channels(view)}
    assert len(domains) == 1

    # One time axis for the whole panel: the top and bottom rulers.
    axes = [
        x["axis"]
        for view in views
        for x in _x_channels(view)
        if isinstance(x.get("axis"), dict)
    ]
    assert [a["orient"] for a in axes] == ["top", "bottom"]
    # Every layer inside the two plots nulls its own x axis. A layer that left
    # it implicit next to a sibling that nulled it would not compile.
    for view in views[1:3]:
        assert all(x["axis"] is None for x in _x_channels(view))


def test_heat_cells_declare_where_they_end() -> None:
    # mark_rect on a continuous x must set x2, or a later cell paints over the
    # ones before it. The wind plot's invisible hit layer is a rect too.
    spec, _ = _build_panel(None)
    board, wind = spec["vconcat"][1], spec["vconcat"][2]
    cells = board["layer"][0]
    assert cells["mark"]["type"] == "rect"
    assert cells["encoding"]["x2"]["field"] == "time_end"
    hits = wind["layer"][-1]
    assert hits["mark"]["type"] == "rect" and hits["mark"]["opacity"] == 0
    assert hits["encoding"]["x2"]["field"] == "time_end"


def test_hour_verdicts_collapse_spots_and_keep_the_counts() -> None:
    """One row per hour, missed as soon as any spot missed, counts preserved."""
    hour = pd.Timestamp("2026-07-12T09:00:00", tz="Europe/Zurich")
    accuracy = pd.DataFrame(
        {
            "spot": ["Silvaplana", "Urnersee", "Silvaplana"],
            "time": [hour, hour, hour + pd.Timedelta(hours=1)],
            "delta": [0.2, 1.6, 0.1],
            "verdict": ["matched", "missed", "matched"],
        }
    )

    graded = rc._hour_verdicts(accuracy)

    assert graded["verdict"].tolist() == ["missed", "matched"]
    assert graded["missed"].tolist() == [1, 0]
    assert graded["pairs"].tolist() == [2, 1]
    assert graded["worst"].tolist() == [1.6, 0.1]
    # The tint spans the hour it grades, so it has to say where that hour ends.
    assert (graded["time_end"] - graded["time"]).unique() == pd.Timedelta(hours=1)


def test_the_verdict_is_a_tint_on_the_ruler_not_a_mark_on_the_board() -> None:
    """Accuracy reads off the time axis; the board is left to the quality cells."""
    spec, _ = _build_panel(None)
    top, board, bottom = spec["vconcat"][0], spec["vconcat"][1], spec["vconcat"][3]

    for ruler in (top, bottom):
        tint = next(
            layer
            for layer in ruler["layer"]
            if layer["mark"]["type"] == "rect"
            and layer["encoding"]["color"]["field"] == "verdict"
        )
        # A rect on a continuous x has to declare its end, and the tint must not
        # draw an axis of its own beside the ruler that does.
        assert tint["encoding"]["x2"]["field"] == "time_end"
        assert tint["encoding"]["x"]["axis"] is None

    assert not [
        layer for layer in board["layer"] if layer["mark"]["type"] == "point"
    ], "the board should carry no accuracy marks now the ruler is tinted"


def test_panel_reruns_on_clicks_only_never_on_hover() -> None:
    """Hover params stay client-side: listening to them would rerun on every move."""
    spec, modes = _build_panel(None)

    assert modes == ["cell", "pin_time"]
    names = {p["name"] for p in spec["params"] if "select" in p}
    assert {"hover_board", "hover_row", "hover_wind"} <= names
    assert not {"hover_board", "hover_row", "hover_wind"} & set(modes)
    # The pin param selects the hour, so a click on empty space still pins one.
    pin = next(p for p in spec["params"] if p["name"] == "pin_time")
    assert pin["select"] == {"type": "point", "fields": ["t_ms"], "on": "click"}


def test_crosshair_spans_both_plots_and_the_hovered_row() -> None:
    # The vertical rule is drawn in both plots for both hover params, so the
    # line follows the pointer across the whole panel; the board also carries
    # the horizontal half, which on a board of spots is the hovered row.
    spec, _ = _build_panel(None)
    board, wind = spec["vconcat"][1], spec["vconcat"][2]

    def filters(view: dict) -> list[str]:
        return [
            layer["transform"][0]["filter"]["param"]
            for layer in view["layer"]
            if layer.get("transform")
        ]

    assert {"hover_board", "hover_wind"} <= set(filters(board))
    assert {"hover_board", "hover_wind"} <= set(filters(wind))
    assert "hover_row" in filters(board)
    row_rule = next(
        layer
        for layer in board["layer"]
        if layer.get("transform")
        and layer["transform"][0]["filter"]["param"] == "hover_row"
    )
    assert row_rule["encoding"]["y"]["field"] == "spot"
    assert "x" not in row_rule["encoding"]


def test_focused_spot_wears_the_location_half_of_the_selector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The focused spot gets an orange row rule and an accented axis label."""
    monkeypatch.setattr(rc, "active", lambda: LIGHT)
    spec, _ = _build_panel(None, focus_spot="Sils")
    board = spec["vconcat"][1]

    row = next(
        layer
        for layer in board["layer"]
        if layer["mark"].get("type") == "rule"
        and not layer.get("transform")
        and "y" in layer["encoding"]
        and "x" not in layer["encoding"]
    )
    assert row["mark"]["color"] == LIGHT.reading
    assert spec["datasets"][row["data"]["name"]] == [{"spot": "Sils"}]

    # The axis label is text on the page surface, so it takes accent_text
    # rather than the mark orange, and only for the focused spot's name.
    axis = board["layer"][0]["encoding"]["y"]["axis"]
    assert axis["labelColor"]["condition"]["test"] == 'datum.value === "Sils"'
    assert axis["labelColor"]["condition"]["value"] == LIGHT.accent_text
    assert axis["labelColor"]["value"] == LIGHT.ink
    assert axis["labelFontWeight"]["condition"]["value"] == 700


def test_unfocused_panel_draws_no_row_rule() -> None:
    """Without a focus spot the board carries only the hover row rule."""
    spec, _ = _build_panel(None)
    board = spec["vconcat"][1]
    plain_row_rules = [
        layer
        for layer in board["layer"]
        if layer["mark"].get("type") == "rule"
        and not layer.get("transform")
        and "y" in layer["encoding"]
    ]
    assert plain_row_rules == []


@pytest.mark.parametrize("palette", [LIGHT, DARK])
def test_pinned_time_is_labelled_on_both_rulers(
    monkeypatch: pytest.MonkeyPatch, palette: object
) -> None:
    """The pin is the time selector, so both ruler edges name the hour it holds."""
    monkeypatch.setattr(rc, "active", lambda: palette)
    hours = _panel_frames()[3]
    spec, _ = _build_panel(hours[4])

    for ruler in (spec["vconcat"][0], spec["vconcat"][-1]):
        marks = {layer["mark"]["type"]: layer["mark"] for layer in ruler["layer"]}
        # The rule is a mark, so it wears the plain reading orange...
        assert marks["rule"]["color"] == palette.reading
        # ...and the label is text, so it takes the role that clears the 4.5:1
        # floor. On the light surface that is a different hex from the mark
        # orange (3.34:1 there); on the dark one the two roles coincide.
        assert marks["text"]["color"] == palette.accent_text
    assert LIGHT.accent_text != LIGHT.reading

    label_data = spec["datasets"][spec["vconcat"][0]["layer"][2]["data"]["name"]]
    assert label_data[0]["label"] == hours[4].strftime("%a %d %b %H:00")


def test_pinned_panel_time_ignores_hours_outside_the_window() -> None:
    start = pd.Timestamp("2026-07-12T06:00:00", tz="Europe/Zurich")
    end = start + pd.Timedelta(hours=6)

    assert rc._pinned_panel_time(start + pd.Timedelta(hours=2), start, end) == (
        start + pd.Timedelta(hours=2)
    )
    # Past the window there is nothing to pin: skipped, so the domain stays put.
    assert rc._pinned_panel_time(end + pd.Timedelta(hours=3), start, end) is None
    assert rc._pinned_panel_time(None, start, end) is None
    # A pin stored in another timezone reads as the same instant.
    assert rc._pinned_panel_time(
        (start + pd.Timedelta(hours=1)).tz_convert("UTC"), start, end
    ) == start + pd.Timedelta(hours=1)


def test_pinned_time_from_event_reads_the_click() -> None:
    tz = "Europe/Zurich"
    hour = pd.Timestamp("2026-07-12T09:00:00", tz=tz)
    event = types.SimpleNamespace(
        selection={"pin_time": [{"t_ms": int(hour.timestamp() * 1000)}]}
    )

    assert rc._pinned_time_from_event(event, tz) == hour
    assert rc._pinned_time_from_event(types.SimpleNamespace(selection={}), tz) is None
    assert rc._pinned_time_from_event(types.SimpleNamespace(), tz) is None


def test_default_detail_row_opens_on_the_pinned_hour() -> None:
    # The details panel is permanent, so with nothing clicked it shows the
    # pinned hour at the focused spot rather than an empty column.
    grid, _, _, hours = _panel_frames()

    row = rc._default_detail_row(grid, "sils", hours[5])
    assert row is not None
    assert row["spot_id"] == "sils"
    assert row["time"] == hours[5]

    # Nothing pinned yet, or no such spot: the panel falls back to its hint.
    assert rc._default_detail_row(grid, "sils", None) is None
    assert rc._default_detail_row(grid, "not-a-spot", hours[5]) is None
    assert rc._default_detail_row(pd.DataFrame(), "sils", hours[5]) is None


def test_elevation_legend_names_the_series_it_draws() -> None:
    _, timeline, _, _ = _panel_frames()
    html = rc._elevation_legend_html(timeline, "Wind & gusts — Silvaplana")

    assert "Wind & gusts — Silvaplana" in html
    assert "10m" in html and "gusts" in html
    # Gusts are told apart by pattern as well as hue.
    assert "dashed" in html
    # A series absent from the frame gets no chip.
    assert "120m" not in html


def test_time_panel_container_wears_a_crosshair_cursor() -> None:
    # The panel reads as a measuring strip, so the pointer over it is a
    # crosshair. The chart's Streamlit key is what the rule hangs off.
    import _styles

    assert "st-key-time_panel_select" in _styles._CSS
    assert "cursor: crosshair" in _styles._CSS


def test_quality_legend_html_draws_the_ramp_as_a_gradient() -> None:
    html = rc._quality_legend_html()

    assert "Session quality (1-5)" in html
    # One strip through the validated anchors, not a chip per level: the fill
    # is continuous, so the legend is too.
    assert "linear-gradient(90deg" in html
    for color in LIGHT.quality:
        assert color in html


def test_compact_dial_uri_follows_the_palette_it_is_given() -> None:
    # The cached grid bakes these URIs, so the mode has to arrive as an
    # argument: resolving it inside would serve one viewer the other's dials.
    args = (200.0, 25.0, 30.0, 45.0, 12.0, True)
    assert rc._compact_dial_uri(*args, LIGHT) != rc._compact_dial_uri(*args, DARK)


_ACCURACY_COLUMNS = ["spot_id", "time", "predicted", "observed", "delta", "verdict"]


def _accuracy_timeline() -> pd.DataFrame:
    """Long-form quality for one spot: three paired hours and one unpaired."""
    times = pd.date_range("2026-07-17T06:00", periods=4, freq="h", tz="UTC")
    rows = [
        (times[0], 4.0, "Predicted (past)"),
        (times[0], 4.0, "Observed"),
        (times[1], 3.0, "Predicted (past)"),
        (times[1], 4.0, "Observed"),
        (times[2], 2.0, "Predicted (past)"),
        (times[2], 4.5, "Observed"),
        # Nothing observed this hour, so it says nothing about accuracy.
        (times[3], 3.5, "Predicted (past)"),
        (times[3], 3.5, "Forecast"),
    ]
    return pd.DataFrame(rows, columns=["time", "quality_index", "series"])


def test_all_spots_accuracy_pairs_hours_and_grades_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        rc, "spot_quality_timeline", lambda *a, **k: _accuracy_timeline()
    )
    rc.all_spots_accuracy.clear()

    frame = rc.all_spots_accuracy(("silvaplana",), "[]")

    assert list(frame.columns) == _ACCURACY_COLUMNS
    # The unpaired hour is dropped; the three paired ones survive, in time order.
    assert len(frame) == 3
    assert frame["spot_id"].unique().tolist() == ["silvaplana"]
    assert frame["delta"].tolist() == [0.0, 1.0, 2.5]
    # A whole band is the cut, so one band off still counts as matched.
    assert frame["verdict"].tolist() == ["matched", "matched", "missed"]


def test_all_spots_accuracy_keeps_its_columns_when_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(rc, "spot_quality_timeline", lambda *a, **k: pd.DataFrame())
    rc.all_spots_accuracy.clear()

    frame = rc.all_spots_accuracy(("silvaplana",), "[]")

    assert frame.empty
    assert list(frame.columns) == _ACCURACY_COLUMNS


def test_hourly_marks_sit_mid_cell() -> None:
    # The board draws an hour as a rect spanning it; the wind series, the
    # crosshair, and the pin mark the same hour as a point, so they sit at the
    # cell's middle rather than on its left edge.
    hours = _panel_frames()[3]
    spec, _ = _build_panel(hours[4])
    board, wind = spec["vconcat"][1], spec["vconcat"][2]

    lines = [v for v in wind["layer"] if v["mark"]["type"] == "line"]
    assert lines and all(v["encoding"]["x"]["field"] == "time_mid" for v in lines)

    hover_rules = [
        v
        for view in (board, wind)
        for v in view["layer"]
        if v["mark"]["type"] == "rule"
        and v.get("transform")
        and v["transform"][0]["filter"]["param"] in ("hover_board", "hover_wind")
        and "x" in v["encoding"]
    ]
    assert hover_rules and all(
        v["encoding"]["x"]["field"] == "t_mid" for v in hover_rules
    )

    pin_rules = [
        v
        for view in (board, wind)
        for v in view["layer"]
        if v["mark"]["type"] == "rule"
        and not v.get("transform")
        and v["encoding"].get("x", {}).get("field") == "time_mid"
    ]
    assert len(pin_rules) == 2  # one in each plot


def test_hover_readout_shows_each_series_value() -> None:
    # Hovering an hour prints every series' own number on the plot, driven by
    # either hover param; the old horizontal rule only marked the 10 m
    # reading's position without saying what it was.
    spec, _ = _build_panel(None)
    wind = spec["vconcat"][2]

    texts = [
        v for v in wind["layer"] if v["mark"]["type"] == "text" and v.get("transform")
    ]
    assert {v["transform"][0]["filter"]["param"] for v in texts} == {
        "hover_board",
        "hover_wind",
    }
    for layer in texts:
        assert layer["encoding"]["text"]["field"] == "wind_speed"
        assert layer["encoding"]["text"]["format"] == ".0f"

    # No y-only hover rule survives in the wind plot.
    y_only = [
        v
        for v in wind["layer"]
        if v["mark"]["type"] == "rule"
        and v.get("transform")
        and "x" not in v["encoding"]
    ]
    assert not y_only


def test_dial_tile_highlights_only_the_selected_spot() -> None:
    selected = rc._dial_tile_html("Silvaplana", "<svg/>", True)
    other = rc._dial_tile_html("Sils", "<svg/>", False)

    assert LIGHT.reading in selected and LIGHT.accent_text in selected
    assert "transparent" in other and LIGHT.reading not in other
    assert "<svg/>" in selected and "Sils" in other
