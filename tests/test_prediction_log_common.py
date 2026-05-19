"""Tests for monitoring._prediction_log_common helpers."""

from __future__ import annotations

import pytest

from foehncast.monitoring._prediction_log_common import (
    _normalized_requested_spot_ids,
    _prediction_log_max_rows,
    _prediction_log_retention_days,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, []),
        ("", []),
        ("  ", []),
        (float("nan"), []),
        ('["silvaplana", "urnersee"]', ["silvaplana", "urnersee"]),
        ("silvaplana,urnersee", ["silvaplana", "urnersee"]),
        ("silvaplana", ["silvaplana"]),
        (42, ["42"]),
    ],
)
def test_normalized_requested_spot_ids(value: object, expected: list[str]) -> None:
    assert _normalized_requested_spot_ids(value) == expected


def test_prediction_log_max_rows_uses_configured_value() -> None:
    assert _prediction_log_max_rows(configured=100) == 100


def test_prediction_log_max_rows_enforces_minimum() -> None:
    assert _prediction_log_max_rows(configured=1) == 2


def test_prediction_log_max_rows_falls_back_to_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FOEHNCAST_PREDICTION_LOG_MAX_ROWS", "50")
    assert _prediction_log_max_rows() == 50


def test_prediction_log_max_rows_handles_invalid_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FOEHNCAST_PREDICTION_LOG_MAX_ROWS", "not-a-number")
    assert _prediction_log_max_rows() == 2048


def test_prediction_log_retention_days_uses_configured_value() -> None:
    assert _prediction_log_retention_days(configured=90) == 90


def test_prediction_log_retention_days_enforces_minimum() -> None:
    assert _prediction_log_retention_days(configured=0) == 1
