"""Tests for the regional wind map: UTC-keyed hourly records and needle lookup."""

from __future__ import annotations

import pathlib
import sys

import pandas as pd
import pytest

# The ui modules import each other by bare name (e.g. `from _wind_map import`),
# so ui/ must be on sys.path before importing the wind map.
_UI = pathlib.Path(__file__).resolve().parents[2] / "ui"
if str(_UI) not in sys.path:
    sys.path.insert(0, str(_UI))

import _wind_map as wm  # noqa: E402


def test_hourly_map_records_resolve_via_utc_and_clamp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Wind frame is Europe/Zurich indexed; the slider hour is a local
    # prediction-window timestamp. Build records once, then resolve both an
    # exact instant and an off-instant that only lands via the clamp.
    tz = "Europe/Zurich"
    times = pd.date_range("2026-07-12T09:00:00", periods=3, freq="h", tz=tz)
    frame = pd.DataFrame(
        {
            "wind_speed_10m": [30.0, 28.0, 25.0],
            "wind_direction_10m": [200.0, 210.0, 220.0],
            "wind_gusts_10m": [40.0, 38.0, 35.0],
        },
        index=times,
    )
    spot = {"id": "silvaplana", "name": "Silvaplana", "lat": 46.45, "lon": 9.79}
    monkeypatch.setattr(wm, "get_spots", lambda: [spot])
    monkeypatch.setattr(wm, "_spot_wind_frame", lambda spot_id: frame)
    wm._hourly_map_records.clear()

    hourly = wm._hourly_map_records(("silvaplana",), 12.0)
    # Keys are the wind frame's UTC isoformat, so both sides agree on the instant.
    assert hourly and all(k.endswith("+00:00") for k in hourly)

    # Exact prediction-window hour (same instant, local tz) resolves to needles.
    exact = wm._lookup_hourly_records(hourly, times[0])
    assert exact["anchors"]

    # An off-instant hour has no exact key and only resolves via the clamp.
    off_hour = times[0] + pd.Timedelta(minutes=20)
    assert wm._to_utc(off_hour).isoformat() not in hourly
    off = wm._lookup_hourly_records(hourly, off_hour)
    assert off["anchors"]
    assert off == exact  # clamped to the nearest available instant

    # No records at all -> empty payload, never a KeyError.
    assert wm._lookup_hourly_records({}, times[0]) == {"anchors": [], "segments": []}
