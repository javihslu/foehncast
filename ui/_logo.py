"""FoehnCast brand mark: a hammock slung between two palm trees, in pixels.

Drawn on a 28x20 grid of whole cells. Palms rather than peaks because a
silhouette has to be identifiable at 130px in a sidebar, and a fronded crown on
a leaning trunk is unmistakable where a triangle is just a triangle.

Motion is frame-based rather than a rotation: swinging pixel art by rotating it
would put marks on half-cells. The sag is a parabola between the two tie
points, so a swing is one number, and the frames differ in depth and lean.

Colours come from _theme, so the mark follows the console's light/dark mode and
inherits the validated contrast rather than carrying its own hexes.

One builder, several outputs. The sidebar embeds this inline; the files under
ui/assets are generated from the same function by scripts/render-brand.py, so
the mark cannot drift between the app and the repo.
"""

from __future__ import annotations

import math

import pandas as pd

from foehncast.solar import solar_elevation_deg

from _theme import Palette, palette

_COLS, _ROWS = 28, 20
_GROUND = 18  # sand fills rows 18-19

# Trunks: base at the sand, leaning apart as they rise, 1 cell thick. The lean
# is what stops two verticals reading as goalposts.
_LEFT_TRUNK = (
    (7, 17),
    (7, 16),
    (7, 15),
    (6, 14),
    (6, 13),
    (6, 12),
    (6, 11),
    (5, 10),
    (5, 9),
    (5, 8),
)
_RIGHT_TRUNK = (
    (20, 17),
    (20, 16),
    (20, 15),
    (21, 14),
    (21, 13),
    (21, 12),
    (21, 11),
    (22, 10),
    (22, 9),
    (22, 8),
    (22, 7),
)

# Crowns: five fronds each, drooping at the tips. Cells are relative to the
# trunk top so both crowns are one shape used twice.
# fmt: off
_CROWN = (
    (-3, 0), (-2, 0), (-1, 0),          # west frond
    (-3, 1),                            # its droop
    (1, 0), (2, 0), (3, 0),             # east frond
    (3, 1),                             # its droop
    (-2, -2), (-1, -1),                 # north-west frond
    (2, -2), (1, -1),                   # north-east frond
    (0, -2), (0, -1),                   # crown centre
)
# fmt: on

# Hammock tie points, partway up each trunk.
_TIE_LEFT, _TIE_RIGHT = (6, 11), (21, 11)
# Sag depth per frame, and a lean that shifts the lowest point along the span.
_SWING = ((5.0, 0.0), (4.6, 0.22), (5.0, 0.0), (4.6, -0.22))
_WIND_ROWS = ((2, 3), (5, 2), (8, 3))
_WIND_FRAMES = 4

# fmt: off
_Z_GLYPH = (
    (0, 0), (1, 0), (2, 0),
            (2, 1),
    (1, 2),
    (0, 3), (1, 3), (2, 3),
)
# fmt: on
_Z_ORIGINS = ((10, 7), (14, 3))

#: Frames in one full loop of the still-frame sequence, for GIF export.
FRAME_COUNT = 4


def _rect(col: int, row: int, color: str) -> str:
    return f'<rect x="{col}" y="{row}" width="1" height="1" fill="{color}"/>'


def _cells(cells: object, color: str) -> str:
    return "".join(_rect(c, r, color) for c, r in cells)  # type: ignore[union-attr]


def _discrete_anim(index: int, count: int, dur: float) -> str:
    """Show this frame for its 1/count slice of the cycle, hide it otherwise."""
    values = ";".join("1" if i == index else "0" for i in range(count))
    return (
        f'<animate attributeName="opacity" values="{values}" dur="{dur}s" '
        f'calcMode="discrete" repeatCount="indefinite"/>'
    )


def _crown_cells(top: tuple[int, int]) -> tuple[tuple[int, int], ...]:
    col, row = top
    return tuple((col + dx, row + dy) for dx, dy in _CROWN)


def _hammock(depth: float, lean: float) -> dict[int, int]:
    """Sag as a parabola between the ties; lean slides its lowest point along."""
    (c0, r0), (c1, r1) = _TIE_LEFT, _TIE_RIGHT
    span = c1 - c0
    out: dict[int, int] = {}
    for col in range(c0, c1 + 1):
        t = (col - c0) / span
        base = r0 + (r1 - r0) * t
        out[col] = round(base + depth * 4 * (t - lean) * (1 - (t - lean)))
    return out


def _fabric(depth: float, lean: float, pal: Palette) -> str:
    frame = _hammock(depth, lean)
    lowest = max(frame.values())
    cells: list[tuple[int, int]] = []
    prev: int | None = None
    for col in sorted(frame):
        row = frame[col]
        # A one-row-per-column diagonal touches only at the corners and reads
        # as a dotted staircase; overlapping each column back to the previous
        # row makes consecutive cells share an edge, so the cloth reads solid.
        top = row if prev is None else min(row, prev)
        cells.extend((col, r) for r in range(top, row + 1))
        # A second cell of cloth along the deepest run gives the fabric bulk.
        if row >= lowest - 1:
            cells.append((col, row + 1))
        prev = row
    return _cells(cells, pal.reading)


def _sky_body(fraction: float, is_day: bool, pal: Palette) -> str:
    """Sun or moon on an east-west arc, placed by how far through the sky it is.

    fraction is 0 at rise and 1 at set, so the mark reads as a clock: low left
    in the morning, overhead at midday, low right before dark.
    """
    f = min(max(fraction, 0.0), 1.0)
    col = round(2 + 23 * f)
    row = round(4 - 3.5 * math.sin(math.pi * f))
    if is_day:
        cells = [(col, row), (col + 1, row), (col, row + 1), (col + 1, row + 1)]
        return "".join(_rect(c, r, pal.sun) for c, r in cells if 0 <= c < _COLS)
    # A bite out of the top-right corner is all a crescent can be at 2x2.
    cells = [(col, row), (col, row + 1), (col + 1, row + 1)]
    return "".join(_rect(c, r, pal.moon) for c, r in cells if 0 <= c < _COLS)


def _zeds(frame: int, pal: Palette) -> str:
    """Two z's showing in turn, so the chain reads as rising rather than blinking."""
    cells = []
    for i, (ox, oy) in enumerate(_Z_ORIGINS):
        if (frame + i) % 2 == 0:
            cells.extend((ox + dx, oy + dy) for dx, dy in _Z_GLYPH)
    return _cells(cells, pal.moon)


def _wind(frame: int, pal: Palette) -> str:
    cells = []
    for i, (row, length) in enumerate(_WIND_ROWS):
        start = (frame * 2 + i * 3) % (_COLS + 6) - 4
        cells.extend((c, row) for c in range(start, start + length) if 0 <= c < _COLS)
    return _cells(cells, pal.gust)


def _scene(pal: Palette) -> str:
    """Sand and the two palms -- everything that does not move."""
    sand = [(c, r) for r in range(_GROUND, _ROWS) for c in range(_COLS)]
    trunks = list(_LEFT_TRUNK) + list(_RIGHT_TRUNK)
    crowns = _crown_cells(_LEFT_TRUNK[-1]) + _crown_cells(_RIGHT_TRUNK[-1])
    return (
        _cells(sand, pal.sand)
        + _cells(trunks, pal.trunk)
        + _cells([c for c in crowns if 0 <= c[0] < _COLS and c[1] >= 0], pal.frond)
    )


def logo_svg(
    size_px: int = 128,
    animate: bool = True,
    title: str = "FoehnCast",
    sky_fraction: float = 0.62,
    is_day: bool = True,
    frame: int = 0,
    dark: bool = False,
) -> str:
    """Inline SVG for the mark.

    animate=True swings the hammock and blows wind via SMIL. With animate=False
    the mark is still, and `frame` picks which step of the loop to draw -- that
    is how the GIF is exported for surfaces that strip SVG animation.
    sky_fraction/is_day place the sun or moon, so the mark shows the same
    daylight the console does.
    """
    pal = palette(dark)
    if animate:
        wind = "".join(
            f'<g opacity="0">{_wind(f, pal)}{_discrete_anim(f, _WIND_FRAMES, 1.8)}</g>'
            for f in range(_WIND_FRAMES)
        )
        fabric = "".join(
            f'<g opacity="0">{_fabric(depth, lean, pal)}'
            f"{_discrete_anim(i, len(_SWING), 2.8)}</g>"
            for i, (depth, lean) in enumerate(_SWING)
        )
        zeds = (
            ""
            if is_day
            else "".join(
                f'<g opacity="0">{_zeds(f, pal)}{_discrete_anim(f, 2, 2.4)}</g>'
                for f in range(2)
            )
        )
    else:
        wind = _wind(frame % _WIND_FRAMES, pal)
        depth, lean = _SWING[frame % len(_SWING)]
        fabric = _fabric(depth, lean, pal)
        zeds = "" if is_day else _zeds(frame % 2, pal)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_COLS} {_ROWS}" '
        f'width="{size_px}" height="{size_px * _ROWS // _COLS}" role="img" '
        f'shape-rendering="crispEdges" '
        f'aria-label="{title}: a hammock slung between two palm trees">'
        f"<title>{title}</title>{wind}{_sky_body(sky_fraction, is_day, pal)}"
        f"{_scene(pal)}{fabric}{zeds}</svg>"
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
