"""Tests for the solar position helpers."""

from __future__ import annotations

import pandas as pd

from foehncast.solar import is_daylight, night_intervals, solar_elevation_deg

ZURICH_LAT, ZURICH_LON = 47.37, 8.54
TZ = "Europe/Zurich"


def test_summer_elevation_high_at_noon_negative_at_midnight() -> None:
    times = pd.DatetimeIndex(
        [
            pd.Timestamp("2026-07-10 13:30", tz=TZ),  # near solar noon
            pd.Timestamp("2026-07-10 01:00", tz=TZ),
        ]
    )
    elevation = solar_elevation_deg(ZURICH_LAT, ZURICH_LON, times)
    assert elevation.iloc[0] > 55
    assert elevation.iloc[1] < -10


def test_summer_night_interval_matches_zurich_sun_times() -> None:
    start = pd.Timestamp("2026-07-10 00:00", tz=TZ)
    end = pd.Timestamp("2026-07-11 00:00", tz=TZ)
    midnight = pd.Timestamp("2026-07-10 02:00", tz=TZ)
    night = next(
        (lo, hi)
        for lo, hi in night_intervals(ZURICH_LAT, ZURICH_LON, start, end)
        if lo <= midnight <= hi
    )
    dawn, dusk_prev = night[1], night[0]
    assert (
        pd.Timestamp("2026-07-10 05:15", tz=TZ)
        <= dawn
        <= pd.Timestamp("2026-07-10 06:15", tz=TZ)
    )
    assert dusk_prev.hour >= 20  # previous evening's dusk after 20:00


def test_winter_daylight_is_short() -> None:
    start = pd.Timestamp("2026-12-21 00:00", tz=TZ)
    end = pd.Timestamp("2026-12-22 00:00", tz=TZ)
    times = pd.date_range(start, end, freq="10min")
    daylight = is_daylight(ZURICH_LAT, ZURICH_LON, times)
    hours = daylight.sum() * 10 / 60
    assert 7.5 <= hours <= 9.5
