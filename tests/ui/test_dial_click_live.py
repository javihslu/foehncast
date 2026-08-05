"""Browser check: the comparison dial itself is the button.

Skipped unless a running console is pointed at, since it drives a real browser.
To run it:

    make ui-fixture
    uv run streamlit run ui/app.py --server.port 8713 --server.headless true
    FOEHNCAST_CONSOLE_URL=http://127.0.0.1:8713 \
        uv run --with playwright pytest tests/ui/test_dial_click_live.py
"""

from __future__ import annotations

import os

import pytest

_URL = os.environ.get("FOEHNCAST_CONSOLE_URL")

pytestmark = pytest.mark.skipif(
    not _URL, reason="set FOEHNCAST_CONSOLE_URL to run the browser check"
)

_TILE = 'div[class*="st-key-dialtile_"]'


def test_clicking_a_dial_switches_the_spot_without_reloading() -> None:
    sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright

    with sync_playwright() as play:
        browser = play.chromium.launch()
        page = browser.new_page(viewport={"width": 1500, "height": 1200})
        page.goto(_URL, timeout=90000)
        page.wait_for_selector(_TILE, timeout=90000)
        page.wait_for_timeout(3000)

        def border(index: int) -> str:
            tile = page.locator(_TILE).nth(index).locator(".fc-dialtile").first
            return tile.get_attribute("style") or ""

        # The second dial is not the focused spot, so its tile has no border.
        assert "transparent" in border(1)

        box = page.locator(_TILE).nth(1).bounding_box()
        # The whole tile answers the pointer, the name row at its foot included.
        for y in (box["y"] + 20, box["y"] + box["height"] - 12):
            tag = page.evaluate(
                "([x, y]) => (document.elementFromPoint(x, y) || {}).tagName",
                [box["x"] + box["width"] / 2, y],
            )
            assert tag == "BUTTON", f"the tile hits {tag} at y={y}"

        # A survivor on the window: a navigation wipes it, a rerun leaves it.
        page.evaluate("window.__stayed = true")
        page.locator(_TILE).nth(1).click()
        page.wait_for_timeout(6000)

        assert page.evaluate("window.__stayed") is True, "the click navigated"
        assert "transparent" not in border(1), "the click did not switch the spot"
        browser.close()
