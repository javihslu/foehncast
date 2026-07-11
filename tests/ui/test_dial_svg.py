"""Test for the compact SVG wind dial builder."""

from __future__ import annotations

import pathlib
import sys

# The ui modules import each other by bare name (e.g. `from _wind_map import`),
# so ui/ must be on sys.path before importing the dial builder.
_UI = pathlib.Path(__file__).resolve().parents[2] / "ui"
if str(_UI) not in sys.path:
    sys.path.insert(0, str(_UI))

from _dial_svg import (  # noqa: E402
    _MIN_NEEDLE_FRAC,
    _R,
    _needle_len,
    wind_dial_svg,
)


def _svg(**overrides: float) -> str:
    base = {
        "direction_deg": 200.0,
        "speed_kn": 18.0,
        "gust_kn": 24.0,
        "shore_orientation_deg": 20.0,
        "min_kts": 12.0,
    }
    base.update(overrides)
    return wind_dial_svg(**base)


def test_wind_dial_svg() -> None:
    svg = _svg()
    assert svg.startswith("<svg")
    for role in ("wedge", "needle", "gust"):
        assert f'data-role="{role}"' in svg
    assert _svg(direction_deg=0.0) != _svg(direction_deg=90.0)  # needle rotates
    assert _needle_len(0.0) == _R * _MIN_NEEDLE_FRAC  # floor: never vanishes
    assert _needle_len(999.0) == _R  # capped at the 30 kn scale
