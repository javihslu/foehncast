"""Shared assertions for Prometheus metric payload tests."""

from __future__ import annotations


def metric_value(payload: str, metric_prefix: str) -> float:
    for line in payload.splitlines():
        if line.startswith(metric_prefix):
            return float(line.split()[-1])
    raise AssertionError(f"Metric not found: {metric_prefix}")