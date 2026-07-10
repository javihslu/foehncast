"""Prometheus export helpers for in-process prediction-monitoring runtime signals.

All metrics in this module are process-local and ephemeral: they are rendered
from in-memory counters that reset whenever the serving process restarts.
Operators should treat them as runtime diagnostics, not durable historical
truth.
"""

from __future__ import annotations

from datetime import datetime
from threading import Lock

from prometheus_client import CollectorRegistry, Counter, Gauge, generate_latest

from foehncast.monitoring._common import timestamp_seconds

_state_lock = Lock()
_schedule_counts: dict[tuple[str, str], int] = {}
_execution_counts: dict[tuple[str, str], int] = {}
_schedule_timestamps: dict[tuple[str, str], float] = {}
_execution_timestamps: dict[tuple[str, str], float] = {}


def _normalized_label(value: str | None) -> str:
    return str(value or "unknown").strip() or "unknown"


def record_prediction_monitoring_schedule(
    endpoint: str,
    result: str,
    *,
    when: datetime | None = None,
) -> None:
    key = (_normalized_label(endpoint), _normalized_label(result))
    with _state_lock:
        _schedule_counts[key] = _schedule_counts.get(key, 0) + 1
        _schedule_timestamps[key] = float(timestamp_seconds(when, default_now=True))


def record_prediction_monitoring_execution(
    endpoint: str,
    result: str,
    *,
    when: datetime | None = None,
) -> None:
    key = (_normalized_label(endpoint), _normalized_label(result))
    with _state_lock:
        _execution_counts[key] = _execution_counts.get(key, 0) + 1
        _execution_timestamps[key] = float(timestamp_seconds(when, default_now=True))


def _reset_prediction_monitoring_state() -> None:
    with _state_lock:
        _schedule_counts.clear()
        _execution_counts.clear()
        _schedule_timestamps.clear()
        _execution_timestamps.clear()


EPHEMERAL_METRIC_PREFIX = "foehncast_prediction_monitoring_"
"""Common prefix for process-local metrics that reset on process restart."""


def build_prediction_counters_prometheus_registry() -> CollectorRegistry:
    """Render in-process prediction-monitoring state into a scrapeable registry."""
    registry = CollectorRegistry()

    schedule_total = Counter(
        "foehncast_prediction_monitoring_schedule_total",
        "Process-local ephemeral (resets on restart). Total prediction-monitoring background task scheduling attempts by endpoint and result.",
        labelnames=("endpoint", "result"),
        registry=registry,
    )
    execution_total = Counter(
        "foehncast_prediction_monitoring_execution_total",
        "Process-local ephemeral (resets on restart). Total prediction-monitoring background task executions by endpoint and result.",
        labelnames=("endpoint", "result"),
        registry=registry,
    )
    last_schedule_timestamp = Gauge(
        "foehncast_prediction_monitoring_last_schedule_timestamp_seconds",
        "Process-local ephemeral (resets on restart). Unix timestamp of the latest prediction-monitoring scheduling event by endpoint and result.",
        labelnames=("endpoint", "result"),
        registry=registry,
    )
    last_execution_timestamp = Gauge(
        "foehncast_prediction_monitoring_last_execution_timestamp_seconds",
        "Process-local ephemeral (resets on restart). Unix timestamp of the latest prediction-monitoring execution event by endpoint and result.",
        labelnames=("endpoint", "result"),
        registry=registry,
    )

    with _state_lock:
        schedule_counts = dict(_schedule_counts)
        execution_counts = dict(_execution_counts)
        schedule_timestamps = dict(_schedule_timestamps)
        execution_timestamps = dict(_execution_timestamps)

    for labels, count in schedule_counts.items():
        schedule_total.labels(*labels).inc(float(count))
    for labels, count in execution_counts.items():
        execution_total.labels(*labels).inc(float(count))
    for labels, timestamp in schedule_timestamps.items():
        last_schedule_timestamp.labels(*labels).set(timestamp)
    for labels, timestamp in execution_timestamps.items():
        last_execution_timestamp.labels(*labels).set(timestamp)

    return registry


def render_prediction_counters_prometheus_metrics() -> bytes:
    """Return Prometheus exposition text for in-process prediction monitoring."""
    registry = build_prediction_counters_prometheus_registry()
    return generate_latest(registry)


__all__ = [
    "EPHEMERAL_METRIC_PREFIX",
    "build_prediction_counters_prometheus_registry",
    "record_prediction_monitoring_execution",
    "record_prediction_monitoring_schedule",
    "render_prediction_counters_prometheus_metrics",
]
