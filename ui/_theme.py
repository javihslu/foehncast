"""Two validated themes for every colour the console draws.

Every value here was computed, not picked. Each mode's marks were swept for the
OKLCH lightness band and chroma floor, then checked for colour-vision
separation and contrast against the surface they actually render on, with
`validate_palette.js` from the data-visualisation method. What the old palette
failed was contrast: the reading dot sat at 2.34:1 on the light surface, well
under the 3:1 floor, which is why the dials were hard to read.

Results held by this file (worst case per mode):

  light, surface #e4efeb   band/reading/night all >= 3:1, CVD dE 10.6,
                           normal-vision dE 24.6, quality ramp light end 2.11:1
  dark,  surface #0c1f24   band/reading/night all >= 3:1, CVD dE 13.5,
                           normal-vision dE 23.8, quality ramp dark end 2.48:1

Re-run the validator if any hex changes. The quality ramp is ordinal, so it is
one hue with monotone lightness, and its anchor flips between modes: level 1 is
the step nearest the surface in both, which means lightest on light and darkest
on dark.

The status roles were added after an audit of the rendered DOM found 33 of 71
text runs under the WCAG floor in dark mode and 18 of 67 in light: components
were writing their own hexes, so the light theme's near-black ink was landing
on the dark surface at 1.06:1. Each role is the worst case over every surface a
status pill actually renders on in its mode, measured with contrast() from the
same validator:

  light  ok 5.39  idle 5.93  warn 5.31  danger 6.08  accent pill 5.82
  dark   ok 5.90  idle 6.00  warn 6.61  danger 5.97  accent pill 5.05

All clear the 4.5:1 floor for normal text. A component that needs a status
colour asks for the role; it must not pick a hex.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    """Colours for one mode. Roles, not names -- callers ask for the job."""

    name: str
    # Surfaces and ink.
    surface: str
    plane_top: str
    plane_bottom: str
    casing: str  # halo drawn under a mark so it survives any background
    ink: str
    ink_secondary: str
    ink_muted: str
    grid: str
    # Marks.
    band: str  # the ideal window: direction range x speed range
    reading: str  # this hour's wind, the dot
    night: str  # sun below the horizon, on a dial dot
    # Session quality on the heatmap: levels 2-5, ordinal, one hue. Level 1 has
    # no step of its own -- a fill that pale cannot clear the light-end floor,
    # so it renders as the bare surface and keeps only its stroke.
    quality: tuple[str, str, str, str]
    night_fill: str  # a night CELL, off the ramp entirely so it claims nothing
    # Wind chart series: three elevations (ordinal) plus gusts (dashed, so it
    # is told apart by pattern rather than by hue alone).
    series: tuple[str, str, str, str]
    # Sky.
    sun: str
    moon: str
    gust: str
    sand: str
    frond: str
    trunk: str
    # Status, as TEXT. Components were writing their own hexes for these, which
    # is how the dark mode ended up with near-black labels on a near-black
    # surface. Each clears 4.5:1 against every surface a status pill actually
    # renders on in its mode, so a component can use the role and stop
    # choosing. They double as the pill's dot, which only needs 3:1.
    status_ink: str  # text on a tinted status pill
    ok: str
    idle: str  # queued, cancelled, neutral-terminal, and secondary detail
    warn: str  # in flight
    danger: str
    # A solid accent that can carry text, for the selected tab pill. The plain
    # band is a mark colour: white on it misses the text floor in both modes.
    accent_solid: str
    on_accent: str

    def rgb(self, hex_value: str) -> list[int]:
        """[R, G, B], the form pydeck layers want."""
        h = hex_value.lstrip("#")
        return [int(h[i : i + 2], 16) for i in (0, 2, 4)]


LIGHT = Palette(
    name="light",
    surface="#f2f8f6",
    plane_top="#eef6f3",
    plane_bottom="#e4efeb",
    casing="#f7faf8",
    ink="#07252a",
    ink_secondary="#38565c",
    ink_muted="#6a848a",
    grid="#cfe0da",
    band="#038c70",
    reading="#d75a07",
    night="#7a4fb5",
    # Kept from the earlier validated light ramp rather than re-stepped:
    # monotone lightness, visible gaps, 2.18:1 light end on this surface.
    quality=("#63b3a4", "#2f9384", "#0f7263", "#084c42"),
    night_fill="#c9c4d6",
    series=("#5fa7a1", "#20837c", "#0b5e60", "#3b5a5a"),
    sun="#e8a300",
    moon="#8ea7ad",
    gust="#8fc7bb",
    sand="#d8c9a6",
    frond="#0f7a62",
    trunk="#8a5a34",
    status_ink="#07252a",
    ok="#0a6357",
    idle="#47535e",
    warn="#8f430c",
    danger="#96271b",
    accent_solid="#0f7263",
    on_accent="#ffffff",
)

DARK = Palette(
    name="dark",
    surface="#0c1f24",
    plane_top="#0c1f24",
    plane_bottom="#071418",
    casing="#12333a",
    ink="#eaf3f1",
    ink_secondary="#a9c3c0",
    ink_muted="#7d9a9c",
    grid="#1d3d44",
    band="#16a384",
    reading="#ea630c",
    night="#9b7fe6",
    # Anchor flips for dark: level 2 is the step nearest the surface.
    # Light end 2.48:1; night_fill clears every step by CVD dE >= 9.2.
    quality=("#276553", "#21826a", "#2b9e81", "#3dbb9a"),
    night_fill="#b9a9e0",
    series=("#7fd4c4", "#46b39f", "#2b8e80", "#9ab3b0"),
    sun="#ffc247",
    moon="#dfe7ea",
    gust="#2f7c73",
    sand="#5a4e36",
    frond="#2b9e81",
    trunk="#a87048",
    status_ink="#eaf3f1",
    ok="#3dbb9a",
    idle="#93aeb0",
    warn="#f0a04b",
    danger="#ff8579",
    accent_solid="#16a384",
    on_accent="#07252a",
)


def tint(hex_value: str, alpha: float) -> str:
    """A translucent wash of a colour, for the pill behind its own status text.

    The wash has to be derived from the role rather than written out per site,
    or the pill and its text drift apart the moment a role changes.
    """
    h = hex_value.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r}, {g}, {b}, {alpha})"


def palette(dark: bool = False) -> Palette:
    return DARK if dark else LIGHT


def is_dark() -> bool:
    """Whether Streamlit is currently rendering in dark mode.

    st.context.theme is the browser-resolved theme, so it follows the viewer's
    own setting rather than whatever the config file happens to declare.
    """
    import streamlit as st

    theme = getattr(st.context, "theme", None)
    return bool(theme is not None and getattr(theme, "type", "light") == "dark")


def active() -> Palette:
    return palette(is_dark())
