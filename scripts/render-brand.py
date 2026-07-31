"""Generate the brand assets under ui/assets from the one builder in ui/_logo.py.

SVG assets are written directly. The GIF needs a browser to rasterise, and is
only for surfaces that strip SVG animation (GitHub READMEs do); pass --gif to
build it, which additionally requires playwright and pillow.

    uv run python scripts/render-brand.py
    uv run --with playwright --with pillow python scripts/render-brand.py --gif
"""

from __future__ import annotations

import argparse
import asyncio
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ui"))

from _logo import FRAME_COUNT, logo_svg  # noqa: E402

ASSETS = ROOT / "ui" / "assets"
GIF_SIZE = 240
GIF_MS = 700


def write_svgs() -> list[pathlib.Path]:
    ASSETS.mkdir(parents=True, exist_ok=True)
    written = []
    for name, kwargs in {
        "foehncast-mark": {"animate": False, "sky_fraction": 0.62},
        "foehncast-mark-animated": {"animate": True, "sky_fraction": 0.62},
        "foehncast-mark-night": {"animate": True, "sky_fraction": 0.45, "is_day": False},
    }.items():
        path = ASSETS / f"{name}.svg"
        path.write_text(logo_svg(size_px=256, **kwargs) + "\n")
        written.append(path)
    return written


async def write_gif() -> pathlib.Path:
    from PIL import Image
    from playwright.async_api import async_playwright

    frames = []
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(
            viewport={"width": GIF_SIZE, "height": GIF_SIZE}, device_scale_factor=2
        )
        for i in range(FRAME_COUNT):
            svg = logo_svg(size_px=GIF_SIZE, animate=False, frame=i)
            await page.set_content(
                f'<body style="margin:0;background:#eef4f2;display:flex;'
                f'align-items:center;justify-content:center;height:{GIF_SIZE}px">'
                f"{svg}</body>"
            )
            await page.wait_for_timeout(120)
            shot = ASSETS / f".frame-{i}.png"
            await page.screenshot(path=str(shot))
            frames.append(Image.open(shot).convert("P", palette=Image.ADAPTIVE))
        await browser.close()

    out = ASSETS / "foehncast-mark.gif"
    frames[0].save(
        out, save_all=True, append_images=frames[1:], duration=GIF_MS, loop=0, optimize=True
    )
    for i in range(FRAME_COUNT):
        (ASSETS / f".frame-{i}.png").unlink(missing_ok=True)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gif", action="store_true", help="also build the animated GIF")
    args = parser.parse_args()

    for path in write_svgs():
        print(f"wrote {path.relative_to(ROOT)}")
    if args.gif:
        print(f"wrote {asyncio.run(write_gif()).relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
