"""Tests for Prometheus export of shadow (A/B) inference divergence."""

from __future__ import annotations

import pytest

from foehncast.monitoring import shadow_prometheus
from tests.prometheus_assertions import metric_value


def _snapshot_with_shadow() -> dict[str, object]:
    return {
        "model_version": "7",
        "predictions": [],
        "shadow": {
            "champion_version": "7",
            "candidate_version": "11",
            "mean_abs_divergence": 0.031,
            "max_abs_divergence": 0.5,
            "compared_rows": 28,
        },
    }


def test_render_shadow_prometheus_metrics_emits_gauges_from_snapshot() -> None:
    payload = shadow_prometheus.render_shadow_prometheus_metrics(
        snapshot=_snapshot_with_shadow(),
    ).decode("utf-8")

    assert metric_value(
        payload, "foehncast_shadow_mean_abs_divergence"
    ) == pytest.approx(0.031)
    assert metric_value(
        payload, "foehncast_shadow_max_abs_divergence"
    ) == pytest.approx(0.5)
    assert metric_value(payload, "foehncast_shadow_compared_rows") == pytest.approx(
        28.0
    )

    info_line = next(
        line
        for line in payload.splitlines()
        if line.startswith("foehncast_shadow_model_info")
    )
    assert 'champion_version="7"' in info_line
    assert 'candidate_version="11"' in info_line
    assert info_line.rstrip().endswith(" 1.0")


def test_render_shadow_prometheus_metrics_empty_without_shadow_section() -> None:
    payload = shadow_prometheus.render_shadow_prometheus_metrics(
        snapshot={"model_version": "7", "predictions": []},
    ).decode("utf-8")

    metric_lines = [
        line for line in payload.splitlines() if line and not line.startswith("#")
    ]
    assert metric_lines == []


def test_render_shadow_prometheus_metrics_empty_without_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shadow_prometheus, "read_latest_predictions", lambda: None)

    payload = shadow_prometheus.render_shadow_prometheus_metrics().decode("utf-8")

    assert payload.strip() == ""


def test_render_shadow_prometheus_metrics_reads_latest_snapshot_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        shadow_prometheus,
        "read_latest_predictions",
        _snapshot_with_shadow,
    )

    payload = shadow_prometheus.render_shadow_prometheus_metrics().decode("utf-8")

    assert metric_value(
        payload, "foehncast_shadow_mean_abs_divergence"
    ) == pytest.approx(0.031)
