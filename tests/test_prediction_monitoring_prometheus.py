"""Tests for Prometheus export of in-process prediction-monitoring state."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from foehncast.monitoring import prediction_monitoring_prometheus


def _metric_value(payload: str, metric_prefix: str) -> float:
    for line in payload.splitlines():
        if line.startswith(metric_prefix):
            return float(line.split()[-1])
    raise AssertionError(f"Metric not found: {metric_prefix}")


@pytest.fixture(autouse=True)
def reset_prediction_monitoring_state() -> None:
    prediction_monitoring_prometheus._reset_prediction_monitoring_state()
    yield
    prediction_monitoring_prometheus._reset_prediction_monitoring_state()


def test_render_prediction_monitoring_prometheus_metrics_uses_endpoint_and_result_labels() -> (
    None
):
    prediction_monitoring_prometheus.record_prediction_monitoring_schedule(
        "predict",
        "scheduled",
        when=datetime(2026, 5, 11, 10, 0, tzinfo=UTC),
    )
    prediction_monitoring_prometheus.record_prediction_monitoring_schedule(
        "rank",
        "failed",
        when=datetime(2026, 5, 11, 10, 5, tzinfo=UTC),
    )
    prediction_monitoring_prometheus.record_prediction_monitoring_execution(
        "predict",
        "succeeded",
        when=datetime(2026, 5, 11, 10, 10, tzinfo=UTC),
    )
    prediction_monitoring_prometheus.record_prediction_monitoring_execution(
        "rank",
        "failed",
        when=datetime(2026, 5, 11, 10, 15, tzinfo=UTC),
    )

    payload = prediction_monitoring_prometheus.render_prediction_monitoring_prometheus_metrics().decode(
        "utf-8"
    )

    assert (
        'foehncast_prediction_monitoring_schedule_total{endpoint="predict",result="scheduled"} 1.0'
        in payload
    )
    assert (
        'foehncast_prediction_monitoring_schedule_total{endpoint="rank",result="failed"} 1.0'
        in payload
    )
    assert (
        'foehncast_prediction_monitoring_execution_total{endpoint="predict",result="succeeded"} 1.0'
        in payload
    )
    assert (
        'foehncast_prediction_monitoring_execution_total{endpoint="rank",result="failed"} 1.0'
        in payload
    )
    assert _metric_value(
        payload,
        'foehncast_prediction_monitoring_last_schedule_timestamp_seconds{endpoint="rank",result="failed"}',
    ) == pytest.approx(1778493900.0)
    assert _metric_value(
        payload,
        'foehncast_prediction_monitoring_last_execution_timestamp_seconds{endpoint="predict",result="succeeded"}',
    ) == pytest.approx(1778494200.0)


def test_render_prediction_monitoring_prometheus_metrics_handles_empty_state() -> None:
    payload = prediction_monitoring_prometheus.render_prediction_monitoring_prometheus_metrics().decode(
        "utf-8"
    )

    assert "foehncast_prediction_monitoring_schedule_total" in payload
    assert "foehncast_prediction_monitoring_execution_total" in payload
