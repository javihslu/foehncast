"""Tests for the pixel brand mark."""

from __future__ import annotations

import pathlib
import sys

import pandas as pd

_UI = pathlib.Path(__file__).resolve().parents[2] / "ui"
if str(_UI) not in sys.path:
    sys.path.insert(0, str(_UI))

from _logo import (  # noqa: E402
    FRAME_COUNT,
    current_sky,
    logo_svg,
)
from _theme import DARK, LIGHT  # noqa: E402


def test_mark_is_whole_pixels_on_the_grid() -> None:
    svg = logo_svg(animate=False)
    assert svg.startswith("<svg")
    assert 'shape-rendering="crispEdges"' in svg
    assert 'width="1" height="1"' in svg  # every mark is one grid cell


def test_sun_by_day_moon_and_zeds_by_night() -> None:
    day = logo_svg(animate=False, is_day=True)
    assert LIGHT.sun in day
    assert LIGHT.moon not in day

    night = logo_svg(animate=False, is_day=False)
    assert LIGHT.sun not in night
    assert LIGHT.moon in night  # moon and the sleep marks share the pale tone


def test_mark_follows_the_theme() -> None:
    light = logo_svg(animate=False, dark=False)
    dark = logo_svg(animate=False, dark=True)
    assert LIGHT.sand in light and DARK.sand in dark
    assert DARK.sand not in light


def test_sky_fraction_moves_the_sun_across() -> None:
    morning = logo_svg(animate=False, sky_fraction=0.05)
    midday = logo_svg(animate=False, sky_fraction=0.5)
    assert morning != midday


def test_frames_differ_so_the_gif_actually_moves() -> None:
    rendered = {logo_svg(animate=False, frame=i) for i in range(FRAME_COUNT)}
    assert len(rendered) > 1


def test_current_sky_is_a_fraction_and_a_daylight_flag() -> None:
    # Silvaplana at local midday in July: sun up, mid-arc.
    noon = pd.Timestamp("2026-07-15T11:00:00", tz="UTC")
    fraction, is_day = current_sky(46.45, 9.79, noon)
    assert is_day is True
    assert 0.0 <= fraction <= 1.0

    midnight = pd.Timestamp("2026-07-15T23:00:00", tz="UTC")
    _, is_day_night = current_sky(46.45, 9.79, midnight)
    assert is_day_night is False
