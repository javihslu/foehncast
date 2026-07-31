"""Shared color tokens for the wind dial.

The regional map (ui/_wind_map.py) and a later small SVG dial both read these,
so the two renderings stay in visual sync. Dial geometry (radius, max kn, wedge
angle) is map-specific and stays in _wind_map.py.
"""

from __future__ import annotations

# Ink for chrome outlines and text.
INK = [7, 37, 42]

# The ideal window: teal wash plus edge, drawn as a band between the ideal
# direction range and the ideal speed range. This is the target, not a reading.
RIDEABLE = [10, 163, 146]

# The reading: one dot at the exact (direction, speed) the forecast gives.
# Orange because it is the complement of the teal target, so the dot never
# disappears into the band it is being compared against. Rideability is read
# from WHERE the dot lands, not from its hue, so this one color serves every
# wind strength. Freed for this use by moving the rider home to a hammock icon.
READING = [255, 122, 38]

# Sun below the horizon. Wind speed is still real at 02:00, so the dot is still
# placed, but calling it a session claims one nobody can have. Darkness is the
# single fact the dot's position cannot carry, so it is the one thing that
# recolors the dot. Validated against the reading orange and the teal band on
# the basemap tone: worst adjacent pair is dE 12.3 (deutan), 16.2 (normal).
NIGHT = [131, 84, 184]

# Light warm-grey casing drawn under needles, rings, and ticks so a mark stays
# legible where it crosses the basemap or another mark (the surface-ring idea).
HALO = [244, 241, 234]

# Ideal-wedge alphas: a readable teal wash under a full-opacity teal edge.
WEDGE_FILL_ALPHA = 110
WEDGE_OUTLINE_ALPHA = 255


def rgb_to_hex(rgb: list[int]) -> str:
    """Convert an [R, G, B] list to a "#rrggbb" string."""
    return "#{:02x}{:02x}{:02x}".format(*rgb)
