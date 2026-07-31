"""FoehnCast brand mark: a hammock slung between two alpine summits, in pixels.

Drawn on a 24x17 grid of whole cells. The stepped silhouette is the point --
at this scale a jagged edge reads as rock where a smooth triangle reads as a
generic marker, so the pixel grid buys the detail instead of costing it.

Motion is frame-based rather than a rotation: swinging pixel art by rotating it
would put marks on half-cells. Three fabric frames and four wind frames are
drawn, and SMIL switches between them discretely.

One builder, two outputs. The sidebar embeds this inline; the files under
ui/assets are generated from the same function by scripts/render-brand.py, so
the mark cannot drift between the app and the repo.
"""

from __future__ import annotations

import math

import pandas as pd

from foehncast.solar import solar_elevation_deg

TEAL = "#0aa392"
TEAL_SHADE = "#07887a"
INK = "#07252a"
INK_LIT = "#123f47"
SNOW = "#f4f1ea"
ORANGE = "#ff7a26"
SUN = "#ffc247"
MOON = "#dfe7ea"
# Wind is drawn a tint lighter than the near massif so a streak in the sky is
# never mistaken for a piece of land.
GUST = "#8fd6cc"

_COLS, _ROWS = 24, 17
_GROUND = 16

# Skyline as the first filled row per column. Asymmetric on purpose: a saddle,
# a steep near flank, a long far shoulder.
_NEAR = {0: 16, 1: 15, 2: 13, 3: 11, 4: 9, 5: 8, 6: 7, 7: 10, 8: 12, 9: 14, 10: 16}
# fmt: off
_FAR = {
    10: 16, 11: 14, 12: 12, 13: 9, 14: 7, 15: 5, 16: 3,
    17: 5, 18: 7, 19: 9, 20: 11, 21: 13, 22: 15, 23: 16,
}
# fmt: on
# Sunlit west flanks, shaded east flanks.
_NEAR_LIT, _FAR_LIT = range(0, 7), range(10, 17)
_NEAR_SNOW = {(6, 7), (6, 8), (5, 8)}
_FAR_SNOW = {(16, 3), (16, 4), (15, 5), (16, 5), (17, 5)}

# The hammock, tied at both summits (cols 6 and 16, which are the two peaks).
# Three frames of sag for the swing.
_FABRIC_FRAMES = (
    {6: 7, 7: 10, 8: 12, 9: 12, 10: 12, 11: 12, 12: 11, 13: 9, 14: 6, 15: 4, 16: 3},
    {6: 7, 7: 10, 8: 11, 9: 12, 10: 12, 11: 13, 12: 12, 13: 9, 14: 6, 15: 4, 16: 3},
    {6: 7, 7: 11, 8: 12, 9: 13, 10: 12, 11: 12, 12: 10, 13: 9, 14: 6, 15: 4, 16: 3},
)
# Cycle: hang, lean right, hang, lean left.
_SWING_ORDER = (0, 1, 0, 2)
# Wind: short streaks crossing the sky, one cell per frame.
_WIND_ROWS = ((1, 3), (4, 2), (2, 3))
_WIND_FRAMES = 4


def _rect(col: int, row: int, color: str) -> str:
    return f'<rect x="{col}" y="{row}" width="1" height="1" fill="{color}"/>'


def _discrete_anim(index: int, count: int, dur: float) -> str:
    """Show this frame for its 1/count slice of the cycle, hide it otherwise."""
    values = ";".join("1" if i == index else "0" for i in range(count))
    return (
        f'<animate attributeName="opacity" values="{values}" dur="{dur}s" '
        f'calcMode="discrete" repeatCount="indefinite"/>'
    )


def _terrain() -> str:
    cells: list[str] = []
    for ridge, lit_cols, lit, shade, snow in (
        (_FAR, _FAR_LIT, INK_LIT, INK, _FAR_SNOW),
        (_NEAR, _NEAR_LIT, TEAL, TEAL_SHADE, _NEAR_SNOW),
    ):
        for col, top in ridge.items():
            for row in range(top, _GROUND + 1):
                if (col, row) in snow:
                    cells.append(_rect(col, row, SNOW))
                else:
                    cells.append(_rect(col, row, lit if col in lit_cols else shade))
    return "".join(cells)


def _fabric(frame: dict[int, int]) -> str:
    cells = []
    for col, row in frame.items():
        cells.append(_rect(col, row, ORANGE))
        # A second cell of cloth where the sag is deepest gives the fabric bulk.
        if row >= 11:
            cells.append(_rect(col, row + 1, ORANGE))
    return "".join(cells)


def _sky_body(fraction: float, is_day: bool) -> str:
    """Sun or moon on an east-west arc, placed by how far through the sky it is.

    fraction is 0 at rise and 1 at set, so the mark reads as a clock: low left
    in the morning, overhead at midday, low right before dark.
    """
    f = min(max(fraction, 0.0), 1.0)
    col = round(2 + 19 * f)
    row = round(4 - 3.5 * math.sin(math.pi * f))
    if is_day:
        cells = [(col, row), (col + 1, row), (col, row + 1), (col + 1, row + 1)]
        return "".join(_rect(c, r, SUN) for c, r in cells if 0 <= c < _COLS)
    # A bite out of the top-right corner is all a crescent can be at 2x2.
    cells = [(col, row), (col, row + 1), (col + 1, row + 1)]
    return "".join(_rect(c, r, MOON) for c, r in cells if 0 <= c < _COLS)


# Sleep marks rising from the hammock, drawn where the valley leaves open sky.
# 3 wide by 4 tall, so the diagonal gets two cells of its own. On a 3x3 the
# diagonal collapses onto the centre and the glyph reads as an I. The origins
# clear both ridges, the hammock, and the moon's arc.
# fmt: off
_Z_GLYPH = (
    (0, 0), (1, 0), (2, 0),
            (2, 1),
    (1, 2),
    (0, 3), (1, 3), (2, 3),
)
# fmt: on
_Z_ORIGINS = ((8, 6), (11, 2))


def _zeds(frame: int) -> str:
    """Two z's fading in turn, so the chain reads as rising rather than blinking."""
    cells = []
    for i, (ox, oy) in enumerate(_Z_ORIGINS):
        if (frame + i) % 2 == 0:
            cells.extend(_rect(ox + dx, oy + dy, MOON) for dx, dy in _Z_GLYPH)
    return "".join(cells)


def _wind(frame: int) -> str:
    cells = []
    for i, (row, length) in enumerate(_WIND_ROWS):
        start = (frame * 2 + i * 3) % (_COLS + 6) - 4
        for col in range(start, start + length):
            if 0 <= col < _COLS:
                cells.append(_rect(col, row, GUST))
    return "".join(cells)


#: Frames in one full loop of the still-frame sequence, for GIF export.
FRAME_COUNT = 4


def logo_svg(
    size_px: int = 128,
    animate: bool = True,
    title: str = "FoehnCast",
    sky_fraction: float = 0.62,
    is_day: bool = True,
    frame: int = 0,
) -> str:
    """Inline SVG for the mark.

    animate=True swings the hammock and blows wind via SMIL. With animate=False
    the mark is still, and `frame` picks which step of the loop to draw -- that
    is how the GIF is exported for surfaces that strip SVG animation.
    sky_fraction/is_day place the sun or moon, so the mark shows the same
    daylight the console does.
    """
    if animate:
        wind = "".join(
            f'<g opacity="0">{_wind(f)}{_discrete_anim(f, _WIND_FRAMES, 1.8)}</g>'
            for f in range(_WIND_FRAMES)
        )
        fabric = "".join(
            f'<g opacity="0">{_fabric(_FABRIC_FRAMES[which])}'
            f"{_discrete_anim(i, len(_SWING_ORDER), 2.8)}</g>"
            for i, which in enumerate(_SWING_ORDER)
        )
        zeds = (
            ""
            if is_day
            else "".join(
                f'<g opacity="0">{_zeds(f)}{_discrete_anim(f, 2, 2.4)}</g>'
                for f in range(2)
            )
        )
    else:
        wind = _wind(frame % _WIND_FRAMES)
        fabric = _fabric(_FABRIC_FRAMES[_SWING_ORDER[frame % len(_SWING_ORDER)]])
        zeds = "" if is_day else _zeds(frame % 2)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_COLS} {_ROWS}" '
        f'width="{size_px}" height="{size_px * _ROWS // _COLS}" role="img" '
        f'shape-rendering="crispEdges" '
        f'aria-label="{title}: a hammock slung between two alpine peaks">'
        f"<title>{title}</title>{wind}{_sky_body(sky_fraction, is_day)}"
        f"{_terrain()}{fabric}{zeds}</svg>"
    )


def current_sky(
    lat: float, lon: float, now: pd.Timestamp | None = None
) -> tuple[float, bool]:
    """How far through the sky the sun is right now, and whether it is up.

    Returns (fraction, is_day). During daylight the fraction runs 0 at sunrise
    to 1 at sunset; at night it runs across the dark hours instead, so the moon
    tracks the same arc.
    """
    now = pd.Timestamp.now(tz="UTC") if now is None else now.tz_convert("UTC")
    times = pd.date_range(
        now.floor("D") - pd.Timedelta(hours=12), periods=48 * 6, freq="10min", tz="UTC"
    )
    lit = solar_elevation_deg(lat, lon, times) > 0.0
    # Walk out from now to the edges of the current lit (or dark) run.
    idx = int(times.searchsorted(now))
    idx = min(max(idx, 0), len(times) - 1)
    state = bool(lit.iloc[idx])
    start = idx
    while start > 0 and bool(lit.iloc[start - 1]) == state:
        start -= 1
    end = idx
    while end < len(times) - 1 and bool(lit.iloc[end + 1]) == state:
        end += 1
    span = max(end - start, 1)
    return (idx - start) / span, state
