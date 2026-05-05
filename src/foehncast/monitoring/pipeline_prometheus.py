"""Prometheus export helpers for persisted feature-pipeline summaries."""

from __future__ import annotations

from typing import Any

import pandas as pd
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Gauge,
    generate_latest,
)

from foehncast.monitoring.pipeline_metrics import (
    read_all_feature_pipeline_run_summaries,
)


def build_feature_pipeline_prometheus_registry(
    summaries: list[dict[str, Any]] | None = None,
) -> CollectorRegistry:
    """Render persisted feature-pipeline summaries into a scrapeable registry."""
    resolved_summaries = (
        read_all_feature_pipeline_run_summaries() if summaries is None else summaries
    )
    registry = CollectorRegistry()

    summary_count = Gauge(
        "foehncast_feature_pipeline_summary_count",
        "Number of persisted feature-pipeline summary files available for scraping.",
        registry=registry,
    )
    summary_count.set(len(resolved_summaries))

    run_success = Gauge(
        "foehncast_feature_pipeline_run_success",
        "Whether the latest feature-pipeline run succeeded for a dataset.",
        labelnames=("dataset", "storage_backend"),
        registry=registry,
    )
    summary_generated = Gauge(
        "foehncast_feature_pipeline_summary_generated_timestamp_seconds",
        "Unix timestamp of the latest persisted feature-pipeline summary.",
        labelnames=("dataset", "storage_backend"),
        registry=registry,
    )
    expected_spots = Gauge(
        "foehncast_feature_pipeline_expected_spot_count",
        "Configured spot count for the latest feature-pipeline summary.",
        labelnames=("dataset", "storage_backend"),
        registry=registry,
    )
    fetched_spots = Gauge(
        "foehncast_feature_pipeline_fetched_spot_count",
        "Fetched spot count for the latest feature-pipeline summary.",
        labelnames=("dataset", "storage_backend"),
        registry=registry,
    )
    stored_spots = Gauge(
        "foehncast_feature_pipeline_stored_spot_count",
        "Stored spot count for the latest feature-pipeline summary.",
        labelnames=("dataset", "storage_backend"),
        registry=registry,
    )
    skipped_spots = Gauge(
        "foehncast_feature_pipeline_skipped_spot_count",
        "Skipped spot count for the latest feature-pipeline summary.",
        labelnames=("dataset", "storage_backend"),
        registry=registry,
    )
    failed_spots = Gauge(
        "foehncast_feature_pipeline_failed_spot_count",
        "Failed spot count for the latest feature-pipeline summary.",
        labelnames=("dataset", "storage_backend"),
        registry=registry,
    )

    ingest_rows = Gauge(
        "foehncast_feature_pipeline_spot_ingest_rows",
        "Fetched ingest row count for one feature-pipeline spot summary.",
        labelnames=("dataset", "storage_backend", "spot_id"),
        registry=registry,
    )
    engineered_rows = Gauge(
        "foehncast_feature_pipeline_spot_engineered_rows",
        "Engineered row count for one feature-pipeline spot summary.",
        labelnames=("dataset", "storage_backend", "spot_id"),
        registry=registry,
    )
    engineered_new_columns = Gauge(
        "foehncast_feature_pipeline_spot_engineered_new_columns",
        "Count of engineered columns added for one feature-pipeline spot summary.",
        labelnames=("dataset", "storage_backend", "spot_id"),
        registry=registry,
    )
    validation_passed = Gauge(
        "foehncast_feature_pipeline_spot_validation_passed",
        "Whether validation passed for one feature-pipeline spot summary.",
        labelnames=("dataset", "storage_backend", "spot_id"),
        registry=registry,
    )
    range_violation_count = Gauge(
        "foehncast_feature_pipeline_spot_range_violation_count",
        "Range violation count for one feature-pipeline spot summary.",
        labelnames=("dataset", "storage_backend", "spot_id"),
        registry=registry,
    )
    stored_rows_metric = Gauge(
        "foehncast_feature_pipeline_spot_stored_rows",
        "Stored row count for one feature-pipeline spot summary.",
        labelnames=("dataset", "storage_backend", "spot_id"),
        registry=registry,
    )
    max_numeric_abs_delta = Gauge(
        "foehncast_feature_pipeline_spot_max_numeric_abs_delta",
        "Maximum absolute numeric round-trip delta for one feature-pipeline spot summary.",
        labelnames=("dataset", "storage_backend", "spot_id"),
        registry=registry,
    )
    time_basis_preserved = Gauge(
        "foehncast_feature_pipeline_spot_time_basis_preserved",
        "Whether the time basis is preserved through storage for one spot.",
        labelnames=("dataset", "storage_backend", "spot_id"),
        registry=registry,
    )
    feast_projection_ready = Gauge(
        "foehncast_feature_pipeline_spot_feast_projection_ready",
        "Whether one feature-pipeline spot summary is ready for Feast projection.",
        labelnames=("dataset", "storage_backend", "spot_id"),
        registry=registry,
    )

    for summary in resolved_summaries:
        dataset = str(summary.get("dataset", "unknown"))
        storage_backend = str(summary.get("storage_backend", "unknown"))
        run_labels = (dataset, storage_backend)

        run_success.labels(*run_labels).set(
            float(summary.get("run_status") == "succeeded")
        )
        generated_at = summary.get("generated_at")
        if generated_at:
            summary_generated.labels(*run_labels).set(
                pd.Timestamp(generated_at).timestamp()
            )
        expected_spots.labels(*run_labels).set(
            float(summary.get("expected_spot_count", 0))
        )
        fetched_spots.labels(*run_labels).set(
            float(summary.get("fetched_spot_count", 0))
        )
        stored_spots.labels(*run_labels).set(float(summary.get("stored_spot_count", 0)))
        skipped_spots.labels(*run_labels).set(
            float(summary.get("skipped_spot_count", 0))
        )
        failed_spots.labels(*run_labels).set(float(summary.get("failed_spot_count", 0)))

        for spot_summary in summary.get("spots", []):
            spot_labels = (
                dataset,
                storage_backend,
                str(spot_summary.get("spot_id", "unknown")),
            )
            ingest_rows.labels(*spot_labels).set(
                float(spot_summary.get("ingest", {}).get("rows", 0))
            )
            engineered_rows.labels(*spot_labels).set(
                float(spot_summary.get("engineering", {}).get("rows", 0))
            )
            engineered_new_columns.labels(*spot_labels).set(
                float(
                    spot_summary.get("engineering", {}).get(
                        "engineered_column_count", 0
                    )
                )
            )
            validation_passed.labels(*spot_labels).set(
                float(spot_summary.get("validation", {}).get("is_valid", False))
            )
            range_violation_count.labels(*spot_labels).set(
                float(
                    spot_summary.get("validation", {}).get("range_violation_count", 0)
                )
            )
            stored_rows_metric.labels(*spot_labels).set(
                float(spot_summary.get("storage", {}).get("stored_rows", 0))
            )
            delta = spot_summary.get("storage", {}).get("max_numeric_abs_delta")
            if delta is not None:
                max_numeric_abs_delta.labels(*spot_labels).set(float(delta))
            time_basis_preserved.labels(*spot_labels).set(
                float(
                    spot_summary.get("storage", {}).get("time_basis_preserved", False)
                )
            )
            feast_projection_ready.labels(*spot_labels).set(
                float(spot_summary.get("feast", {}).get("projection_ready", False))
            )

    return registry


def render_feature_pipeline_prometheus_metrics(
    summaries: list[dict[str, Any]] | None = None,
) -> bytes:
    """Return Prometheus exposition text for the latest feature-pipeline summaries."""
    registry = build_feature_pipeline_prometheus_registry(summaries=summaries)
    return generate_latest(registry)


__all__ = [
    "CONTENT_TYPE_LATEST",
    "build_feature_pipeline_prometheus_registry",
    "render_feature_pipeline_prometheus_metrics",
]
