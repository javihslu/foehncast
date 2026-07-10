"""Prometheus export helpers for hindcast validation metrics.

Reads cached results from the hindcast state file. The actual validation
runs as a periodic background task and writes to that file.
"""

from __future__ import annotations

from typing import Any

from prometheus_client import CollectorRegistry, Gauge, generate_latest

from foehncast.monitoring.hindcast import read_hindcast_result


def build_hindcast_prometheus_registry(
    result: dict[str, Any] | None = None,
) -> CollectorRegistry:
    """Render cached hindcast results as Prometheus gauges."""
    resolved = read_hindcast_result() if result is None else result
    registry = CollectorRegistry()

    accuracy = Gauge(
        "foehncast_hindcast_accuracy",
        "Fraction of past predictions where predicted quality class matched observed.",
        registry=registry,
    )
    mae = Gauge(
        "foehncast_hindcast_mae",
        "Mean absolute error between predicted and observed quality index.",
        registry=registry,
    )
    validated_count = Gauge(
        "foehncast_hindcast_validated_count",
        "Number of prediction/observation pairs validated.",
        registry=registry,
    )

    validated_count.set(float(resolved.get("validated_count", 0)))
    if resolved.get("accuracy") is not None:
        accuracy.set(resolved["accuracy"])
    if resolved.get("mae") is not None:
        mae.set(resolved["mae"])

    return registry


def render_hindcast_prometheus_metrics(
    result: dict[str, Any] | None = None,
) -> bytes:
    """Return Prometheus exposition text for hindcast validation."""
    registry = build_hindcast_prometheus_registry(result=result)
    return generate_latest(registry)


__all__ = [
    "build_hindcast_prometheus_registry",
    "render_hindcast_prometheus_metrics",
]
