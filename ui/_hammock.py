"""Hammock mark: the rider-home pin on the regional map, and the brand glyph.

The map pin used to be an orange dot, which is now what every wind reading is;
a hammock says "home" without spending a color the dials need.
"""

from __future__ import annotations

import base64

from _dial_tokens import HALO, INK, READING, rgb_to_hex

# Slung fabric between two posts, drawn as a crescent so it reads as cloth
# rather than a wire. Deliberately spare: at map-pin size the ground line and
# any tie detail collapse into noise, so only posts and fabric survive.
# Fabric with gathered, upturned ends. Posts are deliberately absent: two
# uprights plus a sag reads as the letter M at pin size, whereas the gathered
# ends are what actually make a hammock recognisable.
_FABRIC = "M 13 21 C 16 35, 32 35, 35 21 C 31 28, 17 28, 13 21 Z"


def hammock_svg(size_px: int = 48) -> str:
    """Standalone hammock on a light disc, sized for a map pin.

    Shallow sag, pointed ends, and clear air beneath: fill the disc and it
    reads as a bowl, add uprights and it reads as the letter M. The two short
    ropes going up and out are what fix it as something slung.
    """
    ink, halo, orange = rgb_to_hex(INK), rgb_to_hex(HALO), rgb_to_hex(READING)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" '
        f'width="{size_px}" height="{size_px}">'
        f'<circle cx="24" cy="24" r="21.5" fill="{halo}" stroke="{ink}" '
        f'stroke-width="2"/>'
        f'<path d="M 13 21 L 9 15 M 35 21 L 39 15" stroke="{ink}" '
        f'stroke-width="1.6" stroke-linecap="round" fill="none"/>'
        f'<path d="{_FABRIC}" fill="{orange}" stroke="{ink}" stroke-width="1.2" '
        f'stroke-linejoin="round"/>'
        f"</svg>"
    )


def hammock_data_uri(size_px: int = 44) -> str:
    """Base64 SVG data URI, the form deck.gl's IconLayer accepts."""
    b64 = base64.b64encode(hammock_svg(size_px).encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"
