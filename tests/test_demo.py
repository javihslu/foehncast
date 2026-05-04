"""Tests for the optional Feast demo page."""

from __future__ import annotations

import pytest

from foehncast.inference_pipeline.demo import render_online_features_demo


def test_render_online_features_demo_includes_spots_and_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "foehncast.inference_pipeline.demo.get_spots",
        lambda: [
            {"id": "silvaplana", "name": "Silvaplana"},
            {"id": "urnersee", "name": "Urnersee"},
        ],
    )

    html = render_online_features_demo()

    assert "Silvaplana (silvaplana)" in html
    assert "Urnersee (urnersee)" in html
    assert "/features/online" in html
    assert "Fetch Online Features" in html
