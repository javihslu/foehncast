"""Tests for the sidebar freshness circles: one age semantic, SVG ring states."""

from __future__ import annotations

import pathlib
import sys

# The ui modules import each other by bare name, so ui/ must be on sys.path.
_UI = pathlib.Path(__file__).resolve().parents[2] / "ui"
if str(_UI) not in sys.path:
    sys.path.insert(0, str(_UI))

import _sidebar as sb  # noqa: E402


def test_center_shows_age_for_both_semantics() -> None:
    # One semantic: the center is the data's age, scheduled or on demand.
    scheduled = sb._freshness_circle_html("Features", 3600.0, scheduled=True)
    on_demand = sb._freshness_circle_html("Inference", 3600.0, scheduled=False)
    for html in (scheduled, on_demand):
        assert ">1h 0m</div>" in html


def test_scheduled_ring_states_and_subtitles() -> None:
    cycle = sb._PREDICTION_CYCLE_SECONDS
    fresh = sb._freshness_circle_html("F", 0.2 * cycle, scheduled=True)
    aging = sb._freshness_circle_html("F", 0.8 * cycle, scheduled=True)
    overdue = sb._freshness_circle_html("F", 1.5 * cycle, scheduled=True)

    assert sb._RING_FRESH in fresh and "next in" in fresh
    assert sb._RING_AGING in aging and "next in" in aging
    assert sb._RING_OVERDUE in overdue and "overdue" in overdue
    # Overdue draws the full unbroken ring: no dash gap, so no notch or seam.
    assert "stroke-dasharray" not in overdue


def test_ring_is_svg_with_rounded_caps_not_conic() -> None:
    html = sb._freshness_circle_html("F", 4000.0, scheduled=True)
    assert "<svg" in html
    assert 'stroke-linecap="round"' in html
    assert "conic-gradient" not in html


def test_on_demand_ring_is_dashed_and_idle() -> None:
    html = sb._freshness_circle_html("I", 7200.0, scheduled=False)
    assert 'stroke-dasharray="2 7"' in html
    assert sb._RING_IDLE in html
    assert "on demand" in html
