"""Dial colours, resolved from the active theme rather than hard-coded.

The dial draws three marks that can sit next to each other -- the ideal band,
the reading dot, and the night recolour of that dot -- so the three are held to
the all-pairs colour-vision and contrast gates in _theme, per mode. Geometry
constants that do not change with theme stay here.
"""

from __future__ import annotations

from dataclasses import dataclass

from _theme import Palette, active

# Ideal-wedge alphas: a readable wash under a full-opacity edge.
WEDGE_FILL_ALPHA = 110
WEDGE_OUTLINE_ALPHA = 255


@dataclass(frozen=True)
class DialTokens:
    """One theme's dial colours, as [R, G, B] lists for pydeck."""

    ink: list[int]
    halo: list[int]  # casing drawn under a mark so it survives any background
    band: list[int]
    reading: list[int]
    night: list[int]

    @property
    def hex(self) -> dict[str, str]:
        return {
            "ink": rgb_to_hex(self.ink),
            "halo": rgb_to_hex(self.halo),
            "band": rgb_to_hex(self.band),
            "reading": rgb_to_hex(self.reading),
            "night": rgb_to_hex(self.night),
        }


def dial_tokens(pal: Palette | None = None) -> DialTokens:
    pal = pal or active()
    return DialTokens(
        ink=pal.rgb(pal.ink),
        halo=pal.rgb(pal.casing),
        band=pal.rgb(pal.band),
        reading=pal.rgb(pal.reading),
        night=pal.rgb(pal.night),
    )


def rgb_to_hex(rgb: list[int]) -> str:
    """Convert an [R, G, B] list to a "#rrggbb" string."""
    return "#{:02x}{:02x}{:02x}".format(*rgb)
