"""Prometheus export helpers for persisted drift reports."""

from __future__ import annotations

from typing import Any

from prometheus_client import CollectorRegistry, Gauge, generate_latest

from foehncast.monitoring._common import safe_float
from foehncast.monitoring.drift import read_all_drift_reports


def build_drift_prometheus_registry(
    reports: list[dict[str, Any]] | None = None,
) -> CollectorRegistry:
    """Render persisted drift reports into a scrapeable Prometheus registry."""
    resolved_reports = read_all_drift_reports() if reports is None else reports
    registry = CollectorRegistry()

    if not resolved_reports:
        return registry

    drift_metric = Gauge(
        "foehncast_drift_metric",
        "Drift detection metric value.",
        labelnames=("dataset_name", "dataset_version", "column_name", "metric_name"),
        registry=registry,
    )

    drift_detected = Gauge(
        "foehncast_feature_pipeline_dataset_drift_detected",
        "Whether dataset-level drift was detected.",
        labelnames=("dataset",),
        registry=registry,
    )

    spot_validation = Gauge(
        "foehncast_feature_pipeline_spot_validation_passed",
        "Whether spot validation passed (inverse of drift).",
        labelnames=("dataset", "spot_id"),
        registry=registry,
    )

    for report in resolved_reports:
        ds_name = str(report.get("dataset_name", "unknown"))
        ds_version = str(report.get("dataset_version", "unknown"))

        drift_metric.labels(
            dataset_name=ds_name,
            dataset_version=ds_version,
            column_name="dataset",
            metric_name="threshold",
        ).set(safe_float(report.get("threshold")) or 0.0)

        drift_metric.labels(
            dataset_name=ds_name,
            dataset_version=ds_version,
            column_name="dataset",
            metric_name="drifted_column_count",
        ).set(safe_float(report.get("drifted_column_count")) or 0.0)

        drift_metric.labels(
            dataset_name=ds_name,
            dataset_version=ds_version,
            column_name="dataset",
            metric_name="share_of_drifted_columns",
        ).set(safe_float(report.get("share_of_drifted_columns")) or 0.0)

        drift_metric.labels(
            dataset_name=ds_name,
            dataset_version=ds_version,
            column_name="dataset",
            metric_name="dataset_drift",
        ).set(1.0 if report.get("dataset_drift") else 0.0)

        drift_detected.labels(dataset=ds_name).set(
            1.0 if report.get("dataset_drift") else 0.0,
        )

        for column_metric in report.get("metrics", []):
            col_name = str(column_metric.get("column_name", "unknown"))
            drift_metric.labels(
                dataset_name=ds_name,
                dataset_version=ds_version,
                column_name=col_name,
                metric_name="drift_detected",
            ).set(1.0 if column_metric.get("drift_detected") else 0.0)

            score = column_metric.get("drift_score")
            if score is not None:
                drift_metric.labels(
                    dataset_name=ds_name,
                    dataset_version=ds_version,
                    column_name=col_name,
                    metric_name="drift_score",
                ).set(safe_float(score) or 0.0)

            col_threshold = column_metric.get("threshold")
            if col_threshold is not None:
                drift_metric.labels(
                    dataset_name=ds_name,
                    dataset_version=ds_version,
                    column_name=col_name,
                    metric_name="threshold",
                ).set(safe_float(col_threshold) or 0.0)

            spot_validation.labels(
                dataset=ds_name,
                spot_id=col_name,
            ).set(0.0 if column_metric.get("drift_detected") else 1.0)

    return registry


def render_drift_prometheus_metrics(
    reports: list[dict[str, Any]] | None = None,
) -> bytes:
    """Render drift metrics in Prometheus exposition format."""
    return generate_latest(build_drift_prometheus_registry(reports))
