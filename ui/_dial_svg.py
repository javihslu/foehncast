"""Compact SVG wind dial for the heatmap tooltip and detail panel.

Mirrors the regional map dial (ui/_wind_map.py): shared colors from
_dial_tokens, the ideal window drawn as a band spanning both the direction
range and the speed range, and one dot at the exact reading. Pure string
builder.
"""

from __future__ import annotations

import math

from _dial_tokens import (
    WEDGE_FILL_ALPHA,
    WEDGE_OUTLINE_ALPHA,
    dial_tokens,
    rgb_to_hex,
)
from _theme import Palette
from _wind_map import (
    _DIAL_MAX_KN as _MAX_KN,
    _IDEAL_HALF_ANGLE_DEG as _HALF_ANGLE_DEG,
    _status,
    ideal_band_kn,
)

_SIZE = 160.0
_CX = _CY = _SIZE / 2.0
_R = 62.0  # outer ring == _MAX_KN on the speed scale, leaving room for ticks


def _pt(r: float, bearing_deg: float) -> tuple[float, float]:
    # Point at radius r on a compass bearing (0=N up, clockwise), in SVG coords.
    a = math.radians(bearing_deg)
    return (_CX + r * math.sin(a), _CY - r * math.cos(a))


def _radius(speed_kn: float) -> float:
    """Speed on the shared 30 kn scale, in SVG units."""
    return _R * min(max(speed_kn, 0.0), _MAX_KN) / _MAX_KN


def _band(r_in: float, r_out: float, a0: float, a1: float) -> str:
    """Annulus sector: the ideal window is a direction range AND a speed range."""
    x0, y0 = _pt(r_out, a0)
    x1, y1 = _pt(r_out, a1)
    x2, y2 = _pt(r_in, a1)
    x3, y3 = _pt(r_in, a0)
    large = 1 if (a1 - a0) % 360 > 180 else 0
    return (
        f"M {x0:.2f} {y0:.2f} "
        f"A {r_out:.2f} {r_out:.2f} 0 {large} 1 {x1:.2f} {y1:.2f} "
        f"L {x2:.2f} {y2:.2f} "
        f"A {r_in:.2f} {r_in:.2f} 0 {large} 0 {x3:.2f} {y3:.2f} Z"
    )


def wind_dial_svg(
    *,
    direction_deg: float,
    speed_kn: float,
    gust_kn: float,
    shore_orientation_deg: float,
    min_kts: float,
    size_px: int = 160,
    detail: str = "full",
    is_day: bool = True,
    band_kn: tuple[float, float] | None = None,
    pal: Palette | None = None,
) -> str:
    """Return an inline SVG dial for one spot at one hour.

    direction_deg is where the wind comes from; the reading dot is placed
    downwind, at the radius its speed earns. Whether the dot sits inside the
    teal band is the rideability answer. detail="compact" drops the ticks,
    cardinal label, and all but one reference ring so the dial fits in a
    heatmap tooltip.
    """
    compact = detail == "compact"
    band = ideal_band_kn() if band_kn is None else band_kn
    flow = (direction_deg + 180.0) % 360.0
    ideal_center = (shore_orientation_deg + 180.0) % 360.0
    status_label = _status(speed_kn, min_kts, is_day, gust_kn=gust_kn)
    tok = dial_tokens(pal)
    dot_hex = rgb_to_hex(tok.reading if is_day else tok.night)
    ink, halo, teal = rgb_to_hex(tok.ink), rgb_to_hex(tok.halo), rgb_to_hex(tok.band)

    # Light casing lifts the outer ring off the panel. Full detail marks
    # 10/20/30 kn; compact keeps a single mid-scale (20 kn) reference ring.
    casing = (
        f'<circle cx="{_CX}" cy="{_CY}" r="{_R:.2f}" fill="none" '
        f'stroke="{halo}" stroke-opacity="0.7" stroke-width="5"/>'
    )
    ring_ks = (20.0,) if compact else (10.0, 20.0, 30.0)
    rings = "".join(
        f'<circle cx="{_CX}" cy="{_CY}" r="{_R * k / _MAX_KN:.2f}" fill="none" '
        f'stroke="{ink}" stroke-opacity="0.22" stroke-width="1"/>'
        for k in ring_ks
    )
    wedge = (
        f'<path d="{_band(_radius(band[0]), _radius(band[1]), ideal_center - _HALF_ANGLE_DEG, ideal_center + _HALF_ANGLE_DEG)}" '
        f'fill="{teal}" fill-opacity="{WEDGE_FILL_ALPHA / 255:.3f}" '
        f'stroke="{teal}" stroke-opacity="{WEDGE_OUTLINE_ALPHA / 255:.3f}" '
        f'stroke-width="1.5" stroke-linejoin="round" data-role="wedge"/>'
    )
    ticks = label = ""
    if not compact:
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

    # Gust tick: a short cross-arc at the gust radius, on the same bearing, so
    # the gap between dot and tick reads as gustiness.
    gr = _radius(gust_kn)
    gx0, gy0 = _pt(gr, flow - 7.0)
    gx1, gy1 = _pt(gr, flow + 7.0)
    gust = (
        f'<line x1="{gx0:.2f}" y1="{gy0:.2f}" x2="{gx1:.2f}" y2="{gy1:.2f}" '
        f'stroke="{dot_hex}" stroke-opacity="0.75" stroke-width="2" '
        f'stroke-linecap="round" data-role="gust"/>'
    )

    # The reading: one dot at (downwind bearing, speed radius), over a surface
    # casing so it stays legible where it crosses the band or a ring.
    dx, dy = _pt(_radius(speed_kn), flow)
    dot_r = 4.5 if compact else 6.0
    dot = (
        f'<circle cx="{_CX}" cy="{_CY}" r="2" fill="{ink}" fill-opacity="0.55"/>'
        f'<circle cx="{dx:.2f}" cy="{dy:.2f}" r="{dot_r + 1.6:.2f}" '
        f'fill="{halo}" fill-opacity="0.9"/>'
        f'<circle cx="{dx:.2f}" cy="{dy:.2f}" r="{dot_r:.2f}" fill="{dot_hex}" '
        f'stroke="{ink}" stroke-opacity="0.35" stroke-width="1" data-role="reading"/>'
    )

    return (
        f'<svg viewBox="0 0 {int(_SIZE)} {int(_SIZE)}" width="{size_px}" '
        f'height="{size_px}" xmlns="http://www.w3.org/2000/svg" role="img" '
        f'aria-label="Wind dial: {speed_kn:.0f} kn, {status_label.lower()}" '
        f'style="display:block;margin:0 auto">'
        f"{casing}{rings}{wedge}{ticks}{label}{gust}{dot}</svg>"
    )
