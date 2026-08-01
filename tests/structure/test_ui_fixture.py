"""Tests for the UI fixture snapshot generator."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "ui_fixture", REPO_ROOT / "scripts" / "ui_fixture.py"
)
ui_fixture = importlib.util.module_from_spec(_spec)
sys.modules["ui_fixture"] = ui_fixture
_spec.loader.exec_module(ui_fixture)


def test_synthetic_payload_covers_every_spot_and_is_deterministic() -> None:
    payload = ui_fixture._synthetic_payload()
    spot_ids = {spot["spot_id"] for spot in payload["predictions"]}

    from foehncast.config import get_spots

    assert spot_ids == {spot["id"] for spot in get_spots()}
    # Quality has to stay inside the band the UI buckets, or cells fall off the ramp.
    values = [
        row["quality_index"]
        for spot in payload["predictions"]
        for row in spot["forecast"]
    ]
    assert all(0.0 <= v <= 5.0 for v in values)
    # A flat board would make the heatmap useless for human checks.
    assert max(values) - min(values) > 1.0
    assert payload == ui_fixture._synthetic_payload()


def test_fixture_payloads_declare_themselves() -> None:
    # model_version is the only field read_latest_predictions carries through to
    # the UI, so it is the one place the banner can key off.
    assert ui_fixture._synthetic_payload()["model_version"] == "fixture"

    captured = {
        "model_version": 16,
        "predictions": [
            {
                "spot_id": "silvaplana",
                "spot_name": "Silvaplana",
                "forecast": [
                    {"time": "2020-01-01T00:00:00+00:00", "quality_index": 3.0},
                    {"time": "2020-01-01T01:00:00+00:00", "quality_index": 4.0},
                ],
            }
        ],
    }
    replayed = ui_fixture._replay(captured)
    assert replayed["model_version"].startswith("fixture")


def test_replay_reanchors_onto_the_current_hour() -> None:
    """A stale capture must land on now, or the charts clip it out of frame."""
    captured = {
        "model_version": 16,
        "predictions": [
            {
                "spot_id": "silvaplana",
                "spot_name": "Silvaplana",
                "forecast": [
                    {"time": "2020-01-01T00:00:00+00:00", "quality_index": 3.0},
                    {"time": "2020-01-01T05:00:00+00:00", "quality_index": 4.0},
                ],
            }
        ],
    }
    rows = ui_fixture._replay(captured)["predictions"][0]["forecast"]
    times = [pd.Timestamp(row["time"]) for row in rows]

    assert times[0] == ui_fixture._anchor()
    # Spacing survives the shift, so the replayed shape matches the capture.
    assert times[1] - times[0] == pd.Timedelta(hours=5)
    assert [row["quality_index"] for row in rows] == [3.0, 4.0]
