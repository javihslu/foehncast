"""Tests for the CSS variables the stylesheet is written against."""

from __future__ import annotations

import pathlib
import sys

import pytest

# The ui modules import each other by bare name, so ui/ must be on sys.path.
_UI = pathlib.Path(__file__).resolve().parents[2] / "ui"
if str(_UI) not in sys.path:
    sys.path.insert(0, str(_UI))

import _styles  # noqa: E402
from _theme import DARK, LIGHT, Palette  # noqa: E402

_VAR_NAMES = (
    "--bg",
    "--surface",
    "--panel",
    "--panel-strong",
    "--ink",
    "--muted",
    "--accent",
    "--accent-soft",
    "--accent-text",
    "--status-ink",
    "--pine",
    "--pine-soft",
    "--warm",
    "--warm-soft",
    "--line",
    "--grid",
    "--shadow",
    "--app-gradient",
)

# The palette fields _root_vars prints verbatim. The rest are rgb()-derived
# washes of ink, band, quality and reading, checked separately below.
_LITERAL_FIELDS = (
    "plane_bottom",
    "plane_top",
    "surface",
    "ink",
    "ink_secondary",
    "band",
    "accent_text",
    "status_ink",
    "reading",
    "grid",
)


@pytest.mark.parametrize("pal", [LIGHT, DARK], ids=lambda p: p.name)
def test_root_vars_emits_every_variable(pal: Palette) -> None:
    css = _styles._root_vars(pal)
    for name in _VAR_NAMES:
        assert f"{name}:" in css


@pytest.mark.parametrize("pal", [LIGHT, DARK], ids=lambda p: p.name)
def test_root_vars_carries_the_mode_own_colours(pal: Palette) -> None:
    css = _styles._root_vars(pal)
    for field in _LITERAL_FIELDS:
        assert getattr(pal, field) in css
    assert pal.quality[2] in css
    # The washes are derived from this mode's ink, not written out per site.
    r, g, b = pal.rgb(pal.ink)
    assert f"rgba({r}, {g}, {b}, 0.18)" in css
    assert f"rgba({r}, {g}, {b}, 0.14)" in css


def test_dark_vars_carry_no_light_ink() -> None:
    # The failure the status roles were added for: a light-mode near-black
    # reaching the dark surface, where it lands at 1.06:1.
    assert LIGHT.ink not in _styles._root_vars(DARK)
    assert DARK.ink not in _styles._root_vars(LIGHT)


def test_inject_styles_writes_the_variables_then_the_sheet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    written: list[str] = []
    monkeypatch.setattr(_styles, "active", lambda: LIGHT)
    monkeypatch.setattr(_styles.st, "markdown", lambda html, **kw: written.append(html))

    assert _styles.inject_styles() is None

    assert len(written) == 2
    assert "--ink:" in written[0]
    assert written[1] == _styles._CSS
