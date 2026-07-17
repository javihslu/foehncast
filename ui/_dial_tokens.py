"""Shared color tokens for the wind dial.

The regional map (ui/_wind_map.py) and a later small SVG dial both read these,
so the two renderings stay in visual sync. Dial geometry (radius, max kn, wedge
angle) is map-specific and stays in _wind_map.py.
"""

from __future__ import annotations

# Ink for chrome outlines and text.
INK = [7, 37, 42]

# Status colors, shared by the needle and the legend chips.
RIDEABLE = [10, 163, 146]
NEAR = [255, 122, 38]
# "Too light" wind: a dark slate that clears 3:1 on the light Carto Positron
# basemap (assumed land tone ~#e8e6e0), replacing the old pale grey that
# vanished on the muted map.
LIGHT_WIND = [78, 92, 104]

# Light warm-grey casing drawn under needles, rings, and ticks so a mark stays
# legible where it crosses the basemap or another mark (the surface-ring idea).
HALO = [244, 241, 234]

# Ideal-wedge alphas: a readable teal wash under a full-opacity teal edge.
WEDGE_FILL_ALPHA = 110
WEDGE_OUTLINE_ALPHA = 255


def rgb_to_hex(rgb: list[int]) -> str:
    """Convert an [R, G, B] list to a "#rrggbb" string."""
    return "#{:02x}{:02x}{:02x}".format(*rgb)
