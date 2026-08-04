"""Test for the compact SVG wind dial builder."""

from __future__ import annotations

import pathlib
import re
import sys

# The ui modules import each other by bare name (e.g. `from _wind_map import`),
# so ui/ must be on sys.path before importing the dial builder.
_UI = pathlib.Path(__file__).resolve().parents[2] / "ui"
if str(_UI) not in sys.path:
    sys.path.insert(0, str(_UI))

from _dial_tokens import dial_tokens, rgb_to_hex  # noqa: E402
from _theme import LIGHT  # noqa: E402
from _dial_svg import (  # noqa: E402
    _R,
    _radius,
    wind_dial_svg,
)


def _svg(**overrides: float) -> str:
    base = {
        "direction_deg": 200.0,
        "speed_kn": 18.0,
        "gust_kn": 24.0,
        "shore_orientation_deg": 20.0,
        "min_kts": 12.0,
        "band_kn": (15.0, 25.0),
        "pal": LIGHT,
    }
    base.update(overrides)
    return wind_dial_svg(**base)


def test_wind_dial_svg() -> None:
    svg = _svg()
    assert svg.startswith("<svg")
    for role in ("wedge", "reading", "gust"):
        assert f'data-role="{role}"' in svg
    assert _svg(direction_deg=0.0) != _svg(direction_deg=90.0)  # dot moves round
    assert _radius(0.0) == 0.0  # the reading is exact: calm plots at the centre
    assert _radius(999.0) == _R  # capped at the 30 kn scale


def test_dot_takes_the_night_color_after_dark() -> None:
    tok = dial_tokens(LIGHT)
    assert rgb_to_hex(tok.reading) in _svg(is_day=True, pal=LIGHT)
    night = _svg(is_day=False, pal=LIGHT)
    assert rgb_to_hex(tok.night) in night
    assert rgb_to_hex(tok.reading) not in night


def test_dial_never_reads_rideable_after_dark() -> None:
    # A strong wind at 02:00 must not come back looking like an afternoon
    # session, in colour or in words. The aria-label carries the same fact,
    # since a screen reader never sees the dot.
    windy = {"speed_kn": 40.0, "min_kts": 15.0}
    tok = dial_tokens(LIGHT)
    day = _svg(**windy, pal=LIGHT)
    night = _svg(**windy, is_day=False, pal=LIGHT)

    def reading_fill(svg: str) -> str:
        # Read the fill off the reading mark itself: other marks share the hue,
        # and stroke attributes sit between fill and data-role, so matching the
        # two as one substring never works.
        mark = re.search(r'<[^>]*data-role="reading"[^>]*>', svg)
        assert mark is not None
        found = re.search(r'fill="(#[0-9a-fA-F]{6})"', mark.group(0))
        assert found is not None
        return found.group(1).lower()

    assert reading_fill(day) == rgb_to_hex(tok.reading).lower()
    assert reading_fill(night) == rgb_to_hex(tok.night).lower()
    assert "night, not rideable" in night.lower()


def test_dial_label_says_when_the_wind_is_too_strong() -> None:
    # Radius saturates at the 30 kn scale, so the label is the only place the
    # dial can say that the wind is past the point of being rideable.
    too_much = _svg(speed_kn=55.0, gust_kn=70.0, min_kts=15.0, pal=LIGHT)
    assert "too strong" in too_much.lower()


def test_compact_dial_is_small_and_label_free() -> None:
    compact = wind_dial_svg(
        direction_deg=200.0,
        speed_kn=18.0,
        gust_kn=24.0,
        shore_orientation_deg=20.0,
        min_kts=12.0,
        size_px=120,
        detail="compact",
        band_kn=(15.0, 25.0),
        pal=LIGHT,
    )
    assert compact.startswith("<svg")
    assert len(compact.encode("utf-8")) <= 1400  # fits the per-cell payload budget
    assert "<text" not in compact  # tick and cardinal labels stripped
    for role in ("wedge", "reading", "gust"):
        assert f'data-role="{role}"' in compact
