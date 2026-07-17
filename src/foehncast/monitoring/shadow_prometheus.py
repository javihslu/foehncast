"""Prometheus export helpers for serving version and shadow (A/B) divergence.

Reads the latest prediction snapshot. The serving model version (the version
that answered the batch) is emitted whenever it is numeric, independently of
the optional shadow section. Shadow scoring runs the candidate against the
champion on the same feature batch during inference; here we just render the
persisted divergence stats. Only the latest snapshot is rendered, so the
champion/candidate label cardinality stays bounded.
"""

from __future__ import annotations

from typing import Any

from prometheus_client import CollectorRegistry, Gauge, generate_latest

from foehncast.inference_pipeline.predict import read_latest_predictions
from foehncast.monitoring._common import (
    registered_model_version_metric_value,
    safe_float,
)


def build_shadow_prometheus_registry(
    snapshot: dict[str, Any] | None = None,
) -> CollectorRegistry:
    """Render the latest snapshot's serving version and shadow divergence."""
    resolved = read_latest_predictions() if snapshot is None else snapshot
    resolved = resolved or {}
    registry = CollectorRegistry()

    serving_version = registered_model_version_metric_value(
        resolved.get("model_version")
    )
    if serving_version is not None:
        serving_model_version = Gauge(
            "foehncast_serving_model_version",
            "Registered model version that served the latest inference batch.",
            registry=registry,
        )
        serving_model_version.set(serving_version)

    shadow = resolved.get("shadow")
    if not shadow:
        return registry

    mean_abs_divergence = Gauge(
        "foehncast_shadow_mean_abs_divergence",
        "Mean absolute divergence between champion and candidate predicted "
        "quality on the latest inference batch.",
        registry=registry,
    )
    max_abs_divergence = Gauge(
        "foehncast_shadow_max_abs_divergence",
        "Maximum absolute divergence between champion and candidate predicted "
        "quality on the latest inference batch.",
        registry=registry,
    )
    compared_rows = Gauge(
        "foehncast_shadow_compared_rows",
        "Number of (spot, horizon) rows compared between champion and candidate "
        "on the latest inference batch.",
        registry=registry,
    )
    model_info = Gauge(
        "foehncast_shadow_model_info",
        "Champion and candidate versions compared in the latest shadow run "
        "(value is always 1).",
        labelnames=("champion_version", "candidate_version"),
        registry=registry,
    )

    mean_abs_divergence.set(safe_float(shadow.get("mean_abs_divergence")) or 0.0)
    max_abs_divergence.set(safe_float(shadow.get("max_abs_divergence")) or 0.0)
    compared_rows.set(safe_float(shadow.get("compared_rows")) or 0.0)
    model_info.labels(
        champion_version=str(shadow.get("champion_version", "unknown")),
        candidate_version=str(shadow.get("candidate_version", "unknown")),
    ).set(1.0)

    return registry


def render_shadow_prometheus_metrics(
    snapshot: dict[str, Any] | None = None,
) -> bytes:
    """Return Prometheus exposition text for the latest shadow divergence."""
    return generate_latest(build_shadow_prometheus_registry(snapshot))


__all__ = [
    "build_shadow_prometheus_registry",
    "render_shadow_prometheus_metrics",
]
