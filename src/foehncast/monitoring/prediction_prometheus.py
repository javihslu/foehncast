"""Prometheus export helpers for durable prediction-event monitoring state."""

from __future__ import annotations

import pandas as pd
from prometheus_client import CollectorRegistry, Gauge, generate_latest

from foehncast.monitoring.prediction_log import read_prediction_history


DURABLE_METRIC_PREFIX = "foehncast_prediction_log_"
"""Common prefix for retained file-backed metrics that survive restarts."""


def build_prediction_log_prometheus_registry(
    predictions_log: pd.DataFrame | None = None,
) -> CollectorRegistry:
    """Render durable prediction-event history into a scrapeable registry."""
    resolved_log = (
        read_prediction_history() if predictions_log is None else predictions_log.copy()
    )
    registry = CollectorRegistry()

    total_rows = Gauge(
        "foehncast_prediction_log_total_row_count",
        "Number of retained durable prediction-event rows available for inference monitoring.",
        registry=registry,
    )
    model_count = Gauge(
        "foehncast_prediction_log_model_count",
        "Number of retained model versions present in durable prediction-event history.",
        registry=registry,
    )
    row_count = Gauge(
        "foehncast_prediction_log_row_count",
        "Retained durable prediction-event row count for one model version.",
        labelnames=("model_version",),
        registry=registry,
    )
    latest_prediction_timestamp = Gauge(
        "foehncast_prediction_log_latest_prediction_timestamp_seconds",
        "Unix timestamp of the latest retained durable prediction-event write for one model version.",
        labelnames=("model_version",),
        registry=registry,
    )
    latest_forecast_timestamp = Gauge(
        "foehncast_prediction_log_latest_forecast_timestamp_seconds",
        "Unix timestamp of the latest retained forecast timestamp in durable prediction-event history for one model version.",
        labelnames=("model_version",),
        registry=registry,
    )

    total_rows.set(float(len(resolved_log)))
    if resolved_log.empty:
        model_count.set(0.0)
        return registry

    grouped = resolved_log.groupby(
        resolved_log["model_version"].astype(str),
        dropna=False,
    )
    model_count.set(float(len(grouped)))

    for model_version, frame in grouped:
        labels = (str(model_version).strip() or "unknown",)
        row_count.labels(*labels).set(float(len(frame)))

        if "prediction_timestamp" in frame.columns:
            prediction_timestamps = pd.to_datetime(
                frame["prediction_timestamp"],
                errors="coerce",
                utc=True,
            )
            if prediction_timestamps.notna().any():
                latest_prediction_timestamp.labels(*labels).set(
                    prediction_timestamps.max().timestamp()
                )

        if "forecast_time" in frame.columns:
            forecast_timestamps = pd.to_datetime(
                frame["forecast_time"],
                errors="coerce",
                utc=True,
            )
            if forecast_timestamps.notna().any():
                latest_forecast_timestamp.labels(*labels).set(
                    forecast_timestamps.max().timestamp()
                )

    return registry


def render_prediction_log_prometheus_metrics(
    predictions_log: pd.DataFrame | None = None,
) -> bytes:
    """Return Prometheus exposition text for durable prediction-event history."""
    registry = build_prediction_log_prometheus_registry(predictions_log=predictions_log)
    return generate_latest(registry)


__all__ = [
    "build_prediction_log_prometheus_registry",
    "DURABLE_METRIC_PREFIX",
    "render_prediction_log_prometheus_metrics",
]
