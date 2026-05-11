"""Tests for Prometheus export of retained prediction-log state."""

from __future__ import annotations

import pandas as pd
import pytest

from foehncast.monitoring import prediction_prometheus


def _metric_value(payload: str, metric_prefix: str) -> float:
    for line in payload.splitlines():
        if line.startswith(metric_prefix):
            return float(line.split()[-1])
    raise AssertionError(f"Metric not found: {metric_prefix}")


def test_render_prediction_log_prometheus_metrics_uses_model_labelled_gauges() -> None:
    predictions_log = pd.DataFrame(
        {
            "model_version": ["7", "7", "8"],
            "prediction_timestamp": pd.to_datetime(
                [
                    "2026-05-11T10:00:00+00:00",
                    "2026-05-11T11:00:00+00:00",
                    "2026-05-11T12:00:00+00:00",
                ],
                utc=True,
            ),
            "forecast_time": pd.to_datetime(
                [
                    "2025-01-01T00:00:00+00:00",
                    "2025-01-01T01:00:00+00:00",
                    "2025-01-01T02:00:00+00:00",
                ],
                utc=True,
            ),
            "quality_index": [2.1, 2.3, 3.1],
        }
    )

    payload = prediction_prometheus.render_prediction_log_prometheus_metrics(
        predictions_log=predictions_log,
    ).decode("utf-8")

    assert "foehncast_prediction_log_total_row_count 3.0" in payload
    assert "foehncast_prediction_log_model_count 2.0" in payload
    assert 'foehncast_prediction_log_row_count{model_version="7"} 2.0' in payload
    assert 'foehncast_prediction_log_row_count{model_version="8"} 1.0' in payload
    assert _metric_value(
        payload,
        'foehncast_prediction_log_latest_prediction_timestamp_seconds{model_version="7"}',
    ) == pytest.approx(1778497200.0)
    assert _metric_value(
        payload,
        'foehncast_prediction_log_latest_forecast_timestamp_seconds{model_version="8"}',
    ) == pytest.approx(1735696800.0)


def test_render_prediction_log_prometheus_metrics_handles_empty_log() -> None:
    payload = prediction_prometheus.render_prediction_log_prometheus_metrics(
        predictions_log=pd.DataFrame(),
    ).decode("utf-8")

    assert "foehncast_prediction_log_total_row_count 0.0" in payload
    assert "foehncast_prediction_log_model_count 0.0" in payload
