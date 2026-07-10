"""Tests for monitoring._common utility helpers."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from foehncast.monitoring._common import (
    registered_model_version_metric_value,
    safe_float,
    timestamp_seconds,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        (float("nan"), None),
        (3.14, 3.14),
        (0, 0.0),
        ("2.5", 2.5),
    ],
)
def test_safe_float(value: object, expected: float | None) -> None:
    assert safe_float(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("", None),
        ("  ", None),
        ("abc", None),
        ("7", 7.0),
        (7, 7.0),
        ("  12 ", 12.0),
    ],
)
def test_registered_model_version_metric_value(
    value: object, expected: float | None
) -> None:
    assert registered_model_version_metric_value(value) == expected


def test_timestamp_seconds_from_none_returns_none() -> None:
    assert timestamp_seconds(None) is None


def test_timestamp_seconds_from_none_with_default_now_returns_current_time() -> None:
    before = datetime.now(UTC).timestamp()
    result = timestamp_seconds(None, default_now=True)
    after = datetime.now(UTC).timestamp()
    assert result is not None
    assert before <= result <= after


def test_timestamp_seconds_from_empty_string_returns_none() -> None:
    assert timestamp_seconds("") is None


def test_timestamp_seconds_from_datetime_object() -> None:
    dt = datetime(2026, 5, 19, 12, 0, 0, tzinfo=UTC)
    assert timestamp_seconds(dt) == dt.timestamp()


def test_timestamp_seconds_from_naive_datetime_assumes_utc() -> None:
    dt = datetime(2026, 5, 19, 12, 0, 0)
    expected = dt.replace(tzinfo=UTC).timestamp()
    assert timestamp_seconds(dt) == expected


def test_timestamp_seconds_from_iso_string() -> None:
    result = timestamp_seconds("2026-05-19T12:00:00+00:00")
    expected = datetime(2026, 5, 19, 12, 0, 0, tzinfo=UTC).timestamp()
    assert result == expected


def test_timestamp_seconds_from_z_suffix_iso_string() -> None:
    result = timestamp_seconds("2026-05-19T12:00:00Z")
    expected = datetime(2026, 5, 19, 12, 0, 0, tzinfo=UTC).timestamp()
    assert result == expected


def test_timestamp_seconds_from_invalid_string_returns_none() -> None:
    assert timestamp_seconds("not-a-timestamp") is None
