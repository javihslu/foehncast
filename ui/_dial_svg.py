"""Compact SVG wind dial for the heatmap detail panel.

Mirrors the regional map dial (ui/_wind_map.py): shared status colors and wedge
alphas from _dial_tokens, ideal wedge from the shore orientation, a downwind
needle scaled to the same 30 kn cap, a gust tick. Pure string builder.
"""

from __future__ import annotations

import math

from _dial_tokens import (
    HALO,
    INK,
    RIDEABLE,
    WEDGE_FILL_ALPHA,
    WEDGE_OUTLINE_ALPHA,
    rgb_to_hex,
)
from _wind_map import (
    _DIAL_MAX_KN as _MAX_KN,
    _IDEAL_HALF_ANGLE_DEG as _HALF_ANGLE_DEG,
    _status,
)

_SIZE = 160.0
_CX = _CY = _SIZE / 2.0
_R = 62.0  # outer ring == _MAX_KN on the speed scale, leaving room for ticks
_MIN_NEEDLE_FRAC = 0.16  # needle floor so a light wind still shows a stub


def _pt(r: float, bearing_deg: float) -> tuple[float, float]:
    # Point at radius r on a compass bearing (0=N up, clockwise), in SVG coords.
    a = math.radians(bearing_deg)
    return (_CX + r * math.sin(a), _CY - r * math.cos(a))


def _offset(x: float, y: float, bearing_deg: float, dist: float) -> tuple[float, float]:
    a = math.radians(bearing_deg)
    return (x + dist * math.sin(a), y - dist * math.cos(a))


def _needle_len(speed_kn: float) -> float:
    # Speed on the 30 kn scale in SVG units, floored so a light wind still shows.
    frac = min(max(speed_kn, 0.0), _MAX_KN) / _MAX_KN
    return max(_R * frac, _R * _MIN_NEEDLE_FRAC)


def _sector(r: float, a0: float, a1: float) -> str:
    x0, y0 = _pt(r, a0)
    x1, y1 = _pt(r, a1)
    large = 1 if (a1 - a0) % 360 > 180 else 0
    return (
        f"M {_CX:.2f} {_CY:.2f} L {x0:.2f} {y0:.2f} "
        f"A {r:.2f} {r:.2f} 0 {large} 1 {x1:.2f} {y1:.2f} Z"
    )


def wind_dial_svg(
    *,
    direction_deg: float,
    speed_kn: float,
    gust_kn: float,
    shore_orientation_deg: float,
    min_kts: float,
    size_px: int = 160,
) -> str:
    """Return an inline SVG dial for one spot at one hour.

    direction_deg is where the wind comes from; the needle is drawn downwind.
    """
    flow = (direction_deg + 180.0) % 360.0
    ideal_center = (shore_orientation_deg + 180.0) % 360.0
    color, status_label = _status(speed_kn, min_kts)
    needle_hex = rgb_to_hex(color)
    ink, halo, teal = rgb_to_hex(INK), rgb_to_hex(HALO), rgb_to_hex(RIDEABLE)

    # Light casing lifts the outer ring off the panel; three rings mark 10/20/30.
    casing = (
        f'<circle cx="{_CX}" cy="{_CY}" r="{_R:.2f}" fill="none" '
        f'stroke="{halo}" stroke-opacity="0.7" stroke-width="5"/>'
    )
    rings = "".join(
        f'<circle cx="{_CX}" cy="{_CY}" r="{_R * k / _MAX_KN:.2f}" fill="none" '
        f'stroke="{ink}" stroke-opacity="0.22" stroke-width="1"/>'
        for k in (10.0, 20.0, 30.0)
    )
    wedge = (
        f'<path d="{_sector(_R, ideal_center - _HALF_ANGLE_DEG, ideal_center + _HALF_ANGLE_DEG)}" '
        f'fill="{teal}" fill-opacity="{WEDGE_FILL_ALPHA / 255:.3f}" '
        f'stroke="{teal}" stroke-opacity="{WEDGE_OUTLINE_ALPHA / 255:.3f}" '
        f'stroke-width="1.5" stroke-linejoin="round" data-role="wedge"/>'
    )
    ticks = ""
    for bearing in (0.0, 90.0, 180.0, 270.0):
        x0, y0 = _pt(_R, bearing)
        x1, y1 = _pt(_R + 5, bearing)
        ticks += (
            f'<line x1="{x0:.2f}" y1="{y0:.2f}" x2="{x1:.2f}" y2="{y1:.2f}" '
            f'stroke="{ink}" stroke-opacity="0.5" stroke-width="1.5"/>'
        )
    nx, ny = _pt(_R + 13, 0.0)
    label = (
        f'<text x="{nx:.2f}" y="{ny:.2f}" text-anchor="middle" '
        f'dominant-baseline="middle" font-family="Manrope, sans-serif" '
        f'font-size="11" font-weight="700" fill="{ink}">N</text>'
    )

    # Gust tick: a short cross-arc at the gust radius, in the needle's status hue.
    gr = min(max(gust_kn, 0.0), _MAX_KN) / _MAX_KN * _R
    gx0, gy0 = _pt(gr, flow - 7.0)
    gx1, gy1 = _pt(gr, flow + 7.0)
    gust = (
        f'<line x1="{gx0:.2f}" y1="{gy0:.2f}" x2="{gx1:.2f}" y2="{gy1:.2f}" '
        f'stroke="{needle_hex}" stroke-width="2" stroke-linecap="round" '
        f'data-role="gust"/>'
    )

    # Needle: surface-tone halo casing under a status-colored shaft, arrowhead,
    # and an ink hub, so it reads over the wedge and rings.
    length = _needle_len(speed_kn)
    tipx, tipy = _pt(length, flow)
    head = min(max(0.25 * length, 6.0), 10.0)
    hx1, hy1 = _offset(tipx, tipy, flow + 150.0, head)
    hx2, hy2 = _offset(tipx, tipy, flow - 150.0, head)
    needle = (
        f'<line x1="{_CX}" y1="{_CY}" x2="{tipx:.2f}" y2="{tipy:.2f}" '
        f'stroke="{halo}" stroke-opacity="0.85" stroke-width="5" '
        f'stroke-linecap="round" data-role="needle-halo"/>'
        f'<line x1="{_CX}" y1="{_CY}" x2="{tipx:.2f}" y2="{tipy:.2f}" '
        f'stroke="{needle_hex}" stroke-width="3" stroke-linecap="round" '
        f'data-role="needle"/>'
        f'<path d="M {tipx:.2f} {tipy:.2f} L {hx1:.2f} {hy1:.2f} '
        f'L {hx2:.2f} {hy2:.2f} Z" fill="{needle_hex}" data-role="needle-head"/>'
        f'<circle cx="{_CX}" cy="{_CY}" r="3" fill="{ink}"/>'
    )

    return (
        f'<svg viewBox="0 0 {int(_SIZE)} {int(_SIZE)}" width="{size_px}" '
        f'height="{size_px}" xmlns="http://www.w3.org/2000/svg" role="img" '
        f'aria-label="Wind dial: {speed_kn:.0f} kn, {status_label.lower()}" '
        f'style="display:block;margin:0 auto">'
        f"{casing}{rings}{wedge}{ticks}{label}{gust}{needle}</svg>"
    )
