"""Test for the compact SVG wind dial builder."""

from __future__ import annotations

import pathlib
import sys

# The ui modules import each other by bare name (e.g. `from _wind_map import`),
# so ui/ must be on sys.path before importing the dial builder.
_UI = pathlib.Path(__file__).resolve().parents[2] / "ui"
if str(_UI) not in sys.path:
    sys.path.insert(0, str(_UI))

from _dial_tokens import NIGHT, READING, rgb_to_hex  # noqa: E402
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
    assert rgb_to_hex(READING) in _svg(is_day=True)
    night = _svg(is_day=False)
    assert rgb_to_hex(NIGHT) in night
    assert rgb_to_hex(READING) not in night


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
    )
    assert compact.startswith("<svg")
    assert len(compact.encode("utf-8")) <= 1400  # fits the per-cell payload budget
    assert "<text" not in compact  # tick and cardinal labels stripped
    for role in ("wedge", "reading", "gust"):
        assert f'data-role="{role}"' in compact
