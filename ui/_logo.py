"""FoehnCast brand mark: a hammock slung between two palm trees, in pixels.

Drawn on a 56x40 grid of whole cells. Palms rather than peaks because a
silhouette has to be identifiable at 130px in a sidebar, and a fronded crown on
a leaning trunk is unmistakable where a triangle is just a triangle.

The grid is fine enough that the trunks carry real thickness and the fronds
curve, so the shapes are generated from a few parameters rather than placed
cell by cell -- changing the scale again means changing the numbers at the top,
not re-authoring every table.

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

_COLS, _ROWS = 56, 40
_GROUND = 36  # sand fills rows 36-39

# Trunks: base at the sand, leaning apart as they rise, two cells thick. The
# lean is what stops two verticals reading as goalposts. Each entry is
# (base column, base row, top row, lean direction); one column of lean is
# spent every _TRUNK_RISE rows.
_TRUNK_RISE = 4
_LEFT_STEM = (14, 35, 16, -1)
_RIGHT_STEM = (40, 35, 14, 1)
_TRUNK_THICK = 2

# Crown: one half, mirrored across the trunk's two-cell width, so both palms
# are the same shape used twice and neither can drift from the other. Each
# frond is a chain of waypoints rather than loose cells -- stepping diagonally
# one cell at a time leaves marks touching only at their corners, which reads
# as a dotted stipple instead of a leaf. Offsets are from the trunk's top-left
# cell; a mirrored cell is (1 - dx, dy).
# fmt: off
_CROWN_HALF = (
    ((0, -1), (0, -6)),              # centre tuft, tying the crown to the trunk
    ((-1, 0), (-3, 0), (-6, 2)),     # low frond, sweeping out then drooping
    ((-1, -2), (-3, -3), (-6, -4)),  # mid frond, reaching out
    ((-1, -4), (-3, -6), (-4, -8)),  # upper frond, reaching up
)
# fmt: on

# Hammock tie points, partway up each trunk: the inner face of each stem.
_TIE_LEFT, _TIE_RIGHT = (12, 22), (43, 22)
# Sag depth per frame, and a lean that shifts the lowest point along the span.
_SWING = ((10.0, 0.0), (9.2, 0.22), (10.0, 0.0), (9.2, -0.22))
_WIND_ROWS = ((5, 8), (11, 5), (19, 7))
_WIND_FRAMES = 4
_SKY_SIZE = 4  # the sun and moon are drawn in a 4x4 box

# fmt: off
_Z_GLYPH = (
    (0, 0), (1, 0), (2, 0), (3, 0), (4, 0), (5, 0),
                                    (4, 1), (5, 1),
                            (3, 2), (4, 2),
                    (2, 3), (3, 3),
            (1, 4), (2, 4),
    (0, 5), (1, 5),
    (0, 6), (1, 6), (2, 6), (3, 6), (4, 6), (5, 6),
)
# fmt: on
_Z_ORIGINS = ((20, 14), (28, 6))

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


def _trunk_cells(stem: tuple[int, int, int, int]) -> tuple[tuple[int, int], ...]:
    """Cells of one leaning trunk, from the sand up to its top row."""
    base_col, base_row, top_row, lean = stem
    cells = []
    for i in range(base_row - top_row + 1):
        col = base_col + lean * (i // _TRUNK_RISE)
        cells.extend((col + t, base_row - i) for t in range(_TRUNK_THICK))
    return tuple(cells)


def _chain(points: tuple[tuple[int, int], ...]) -> list[tuple[int, int]]:
    """Cells along a run of waypoints, every step sharing an edge with the last."""
    cells = [points[0]]
    for x1, y1 in points[1:]:
        x, y = cells[-1]
        while (x, y) != (x1, y1):
            if x != x1:
                x += 1 if x1 > x else -1
                cells.append((x, y))
            if y != y1:
                y += 1 if y1 > y else -1
                cells.append((x, y))
    return cells


def _crown_cells(top: tuple[int, int]) -> tuple[tuple[int, int], ...]:
    """Both halves of a crown, mirrored across the trunk's two-cell width."""
    col, row = top
    cells = []
    for frond in _CROWN_HALF:
        for dx, dy in _chain(frond):
            cells.append((col + dx, row + dy))
            cells.append((col + 1 - dx, row + dy))
    return tuple(cells)


def _disc(size: int, shift: float = 0.0) -> set[tuple[int, int]]:
    """Cells of a circle inscribed in a size x size box, optionally shifted."""
    centre = (size - 1) / 2
    radius = size / 2 - 0.35
    return {
        (x, y)
        for y in range(size)
        for x in range(size)
        if math.hypot(x - centre - shift, y - centre) <= radius
    }


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
        if row >= lowest - 2:
            cells.append((col, row + 1))
        prev = row
    return _cells(cells, pal.reading)


def _sky_body(fraction: float, is_day: bool, pal: Palette) -> str:
    """Sun or moon on an east-west arc, placed by how far through the sky it is.

    fraction is 0 at rise and 1 at set, so the mark reads as a clock: low left
    in the morning, overhead at midday, low right before dark.
    """
    f = min(max(fraction, 0.0), 1.0)
    col = round(4 + 46 * f)
    row = round(8 - 7 * math.sin(math.pi * f))
    disc = _disc(_SKY_SIZE)
    if is_day:
        cells = sorted(disc)
        colour = pal.sun
    else:
        # The crescent is the disc minus a second disc set off to the east.
        cells = sorted(disc - _disc(_SKY_SIZE, shift=1.7))
        colour = pal.moon
    return "".join(
        _rect(col + dx, row + dy, colour) for dx, dy in cells if 0 <= col + dx < _COLS
    )


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
        start = (frame * 4 + 6 + i * 18) % (_COLS + 12) - 8
        cells.extend((c, row) for c in range(start, start + length) if 0 <= c < _COLS)
    return _cells(cells, pal.gust)


def _scene(pal: Palette) -> str:
    """Sand and the two palms -- everything that does not move."""
    sand = [(c, r) for r in range(_GROUND, _ROWS) for c in range(_COLS)]
    left, right = _trunk_cells(_LEFT_STEM), _trunk_cells(_RIGHT_STEM)
    trunks = list(left) + list(right)
    crowns = _crown_cells(left[-_TRUNK_THICK]) + _crown_cells(right[-_TRUNK_THICK])
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
