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


def test_compass_maps_degrees_to_cardinal_labels() -> None:
    assert wm._compass(0.0) == "N"
    assert wm._compass(90.0) == "E"
    assert wm._compass(225.0) == "SW"
    assert wm._compass(359.0) == "N"  # wraps back to N just below 360


def test_status_thresholds_speed_against_minimum() -> None:
    min_kts = 15.0

    assert wm._status(20.0, min_kts) == (wm._COLOR_RIDEABLE, "Rideable")
    assert wm._status(15.0, min_kts) == (wm._COLOR_RIDEABLE, "Rideable")
    assert wm._status(11.0, min_kts) == (wm._COLOR_NEAR, "Almost")  # >= 0.7 * min_kts
    assert wm._status(5.0, min_kts) == (wm._COLOR_LIGHT, "Too light")


def test_to_utc_localizes_naive_and_converts_aware() -> None:
    naive = pd.Timestamp("2026-07-12T09:00:00")
    localized = wm._to_utc(naive)
    assert localized == pd.Timestamp("2026-07-12T09:00:00", tz="UTC")
    assert str(localized.tz) == "UTC"

    aware = pd.Timestamp("2026-07-12T11:00:00", tz="Europe/Zurich")  # CEST, UTC+2
    converted = wm._to_utc(aware)
    assert converted == aware  # same instant
    assert str(converted.tz) == "UTC"
    assert converted.hour == 9


def test_needle_records_returns_anchor_and_four_segments() -> None:
    spot = {"name": "Silvaplana", "lat": 46.45, "lon": 9.79}
    row = pd.Series(
        {"wind_speed_10m": 40.0, "wind_gusts_10m": 55.0, "wind_direction_10m": 200.0}
    )
    min_kts = 15.0

    anchor, segments = wm._needle_records(spot, row, min_kts)

    assert set(anchor) == {
        "lat",
        "lon",
        "label_lon",
        "label_lat",
        "speed_label",
        "tooltip",
    }
    assert anchor["lat"] == spot["lat"]
    assert anchor["lon"] == spot["lon"]

    assert len(segments) == 4
    for seg in segments:
        assert set(seg) == {
            "from_lon",
            "from_lat",
            "to_lon",
            "to_lat",
            "color",
            "width",
        }

    # The needle shaft starts at the spot itself and points along the
    # downwind bearing (direction + 180, always in [0, 360) by construction).
    shaft = segments[0]
    assert shaft["from_lon"] == spot["lon"]
    assert shaft["from_lat"] == spot["lat"]
    speed_kn = 40.0 / wm._KN_TO_KMH
    flow = (200.0 + 180.0) % 360.0
    assert 0.0 <= flow < 360.0
    expected_tip = wm._destination(
        spot["lat"], spot["lon"], flow, wm._dial_radius_km(speed_kn)
    )
    assert shaft["to_lon"] == pytest.approx(expected_tip[0])
    assert shaft["to_lat"] == pytest.approx(expected_tip[1])

    # 40 km/h (~22 kn) clears a 15 kn minimum -> rideable status color.
    assert shaft["color"] == wm._COLOR_RIDEABLE
    assert anchor["speed_label"] == f"{speed_kn:.0f} kn"
    assert "from S" in anchor["tooltip"]
    assert anchor["tooltip"].endswith("Rideable")


def test_dial_radius_km_scales_with_speed_and_caps_at_max() -> None:
    assert wm._dial_radius_km(0.0) == 0.0
    assert wm._dial_radius_km(15.0) == pytest.approx(wm._DIAL_RADIUS_KM * 0.5)
    assert wm._dial_radius_km(30.0) == wm._DIAL_RADIUS_KM
    assert wm._dial_radius_km(999.0) == wm._DIAL_RADIUS_KM  # capped, never overshoots


def test_destination_bearing_zero_moves_north() -> None:
    lat, lon = 46.45, 9.79
    dest = wm._destination(lat, lon, 0.0, 10.0)

    assert dest[1] > lat
    assert dest[0] == pytest.approx(lon)
    assert dest[1] == pytest.approx(lat + 10.0 / 110.574)
