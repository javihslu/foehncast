"""Test that the heatmap grid carries the tooltip header, dial, and metrics."""

from __future__ import annotations

import json
import pathlib
import sys

import pandas as pd
import pytest

# The ui modules import each other by bare name, so ui/ must be on sys.path.
_UI = pathlib.Path(__file__).resolve().parents[2] / "ui"
if str(_UI) not in sys.path:
    sys.path.insert(0, str(_UI))

import _rider_console as rc  # noqa: E402


def test_all_spots_quality_grid_adds_tooltip_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    times = pd.date_range("2026-07-12T09:00:00Z", periods=3, freq="h")

    def fake_timeline(spot_id: str, *args: object, **kwargs: object) -> pd.DataFrame:
        rows = []
        for t in times:
            rows.append({"time": t, "elevation": "10m", "wind_speed": 22.0})
            rows.append({"time": t, "elevation": "gusts", "wind_speed": 30.0})
        return pd.DataFrame(rows)

    def fake_wind_frame(spot_id: str) -> pd.DataFrame:
        return pd.DataFrame({"wind_direction_10m": [200.0, 210.0, 220.0]}, index=times)

    monkeypatch.setattr(rc, "focus_spot_timeline", fake_timeline)
    monkeypatch.setattr(rc, "_spot_wind_frame", fake_wind_frame)

    predictions = [
        {
            "spot_id": "silvaplana",
            "forecast": [
                {"time": t.isoformat(), "quality_index": q}
                for t, q in zip(times, [4.2, 3.1, 1.5])
            ],
        }
    ]
    ranked = [
        {
            "spot_id": "silvaplana",
            "quality_label": "Firing",
            "quality_index": 4.2,
            "rideable_hours": 5,
            "drive_minutes": 90.0,
            "session_hours": 3.0,
            "ride_drive_ratio": 1.4,
            "score": 0.812,
        }
    ]

    grid = rc.all_spots_quality_grid(
        ("silvaplana",),
        json.dumps(predictions),
        "Europe/Zurich",
        json.dumps(ranked),
    )

    new_columns = ("header", "dial", "direction", "quality_label", "score")
    for col in new_columns:
        assert col in grid.columns
    assert grid["dial"].iloc[0].startswith("data:image/svg+xml;base64,")
    assert grid["header"].iloc[0].startswith("Silvaplana - ")
