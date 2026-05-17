"""Prometheus export helpers for hindcast validation metrics."""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Gauge, generate_latest

from foehncast.monitoring.hindcast import run_hindcast_validation


def build_hindcast_prometheus_registry() -> CollectorRegistry:
    """Run hindcast validation and expose results as Prometheus gauges."""
    result = run_hindcast_validation()
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

    validated_count.set(float(result["validated_count"]))
    if result["accuracy"] is not None:
        accuracy.set(result["accuracy"])
    if result["mae"] is not None:
        mae.set(result["mae"])

    return registry


def render_hindcast_prometheus_metrics() -> bytes:
    """Return Prometheus exposition text for hindcast validation."""
    registry = build_hindcast_prometheus_registry()
    return generate_latest(registry)


__all__ = [
    "build_hindcast_prometheus_registry",
    "render_hindcast_prometheus_metrics",
]
