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
    FEATURE_PIPELINE_STAGES,
    TRAINING_PIPELINE_STAGES,
    read_all_feature_pipeline_run_summaries,
    read_all_training_pipeline_run_summaries,
)


_STAGE_STATE_VALUES = {
    "failed": -1.0,
    "not_run": 0.0,
    "succeeded": 1.0,
}


def _stage_state_value(stage: str, summary: dict[str, Any]) -> float:
    stage_states = dict(summary.get("stage_states", {}))
    if stage in stage_states:
        return _STAGE_STATE_VALUES.get(str(stage_states[stage]), 0.0)

    if int(dict(summary.get("stage_failure_counts", {})).get(stage, 0)) > 0:
        return _STAGE_STATE_VALUES["failed"]
    if stage in dict(summary.get("stage_durations_seconds", {})):
        return _STAGE_STATE_VALUES["succeeded"]
    return _STAGE_STATE_VALUES["not_run"]


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
    engineered_spots = Gauge(
        "foehncast_feature_pipeline_engineered_spot_count",
        "Engineered spot count for the latest feature-pipeline summary.",
        labelnames=("dataset", "storage_backend"),
        registry=registry,
    )
    validated_spots = Gauge(
        "foehncast_feature_pipeline_validated_spot_count",
        "Validated spot count for the latest feature-pipeline summary.",
        labelnames=("dataset", "storage_backend"),
        registry=registry,
    )
    stage_duration = Gauge(
        "foehncast_feature_pipeline_stage_duration_seconds",
        "Stage duration in seconds for the latest feature-pipeline summary.",
        labelnames=("dataset", "storage_backend", "stage"),
        registry=registry,
    )
    stage_failure_count = Gauge(
        "foehncast_feature_pipeline_stage_failure_count",
        "Stage failure count for the latest feature-pipeline summary.",
        labelnames=("dataset", "storage_backend", "stage"),
        registry=registry,
    )
    stage_state = Gauge(
        "foehncast_feature_pipeline_stage_state",
        "Latest feature-pipeline stage state (-1 failed, 0 not run, 1 succeeded).",
        labelnames=("dataset", "storage_backend", "stage"),
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
        engineered_spots.labels(*run_labels).set(
            float(summary.get("engineered_spot_count", 0))
        )
        validated_spots.labels(*run_labels).set(
            float(summary.get("validated_spot_count", 0))
        )
        for stage, duration in dict(summary.get("stage_durations_seconds", {})).items():
            stage_duration.labels(dataset, storage_backend, str(stage)).set(
                float(duration)
            )
        for stage, count in dict(summary.get("stage_failure_counts", {})).items():
            stage_failure_count.labels(dataset, storage_backend, str(stage)).set(
                float(count)
            )
        for stage in FEATURE_PIPELINE_STAGES:
            stage_state.labels(dataset, storage_backend, stage).set(
                _stage_state_value(stage, summary)
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


def build_training_pipeline_prometheus_registry(
    summaries: list[dict[str, Any]] | None = None,
) -> CollectorRegistry:
    """Render persisted training-pipeline summaries into a scrapeable registry."""
    resolved_summaries = (
        read_all_training_pipeline_run_summaries() if summaries is None else summaries
    )
    registry = CollectorRegistry()

    summary_count = Gauge(
        "foehncast_training_pipeline_summary_count",
        "Number of persisted training-pipeline summary files available for scraping.",
        registry=registry,
    )
    summary_count.set(len(resolved_summaries))

    run_success = Gauge(
        "foehncast_training_pipeline_run_success",
        "Whether the latest training-pipeline run succeeded for a dataset and requested stage.",
        labelnames=("dataset", "requested_stage"),
        registry=registry,
    )
    summary_generated = Gauge(
        "foehncast_training_pipeline_summary_generated_timestamp_seconds",
        "Unix timestamp of the latest persisted training-pipeline summary.",
        labelnames=("dataset", "requested_stage"),
        registry=registry,
    )
    stage_duration = Gauge(
        "foehncast_training_pipeline_stage_duration_seconds",
        "Stage duration in seconds for the latest training-pipeline summary.",
        labelnames=("dataset", "requested_stage", "stage"),
        registry=registry,
    )
    stage_failure_count = Gauge(
        "foehncast_training_pipeline_stage_failure_count",
        "Stage failure count for the latest training-pipeline summary.",
        labelnames=("dataset", "requested_stage", "stage"),
        registry=registry,
    )
    stage_state = Gauge(
        "foehncast_training_pipeline_stage_state",
        "Latest training-pipeline stage state (-1 failed, 0 not run, 1 succeeded).",
        labelnames=("dataset", "requested_stage", "stage"),
        registry=registry,
    )
    row_count = Gauge(
        "foehncast_training_pipeline_row_count",
        "Total labelled row count used by the latest training run.",
        labelnames=("dataset", "requested_stage"),
        registry=registry,
    )
    feature_count = Gauge(
        "foehncast_training_pipeline_feature_count",
        "Feature column count used by the latest training run.",
        labelnames=("dataset", "requested_stage"),
        registry=registry,
    )
    train_row_count = Gauge(
        "foehncast_training_pipeline_train_row_count",
        "Training-split row count for the latest training run.",
        labelnames=("dataset", "requested_stage"),
        registry=registry,
    )
    test_row_count = Gauge(
        "foehncast_training_pipeline_test_row_count",
        "Test-split row count for the latest training run.",
        labelnames=("dataset", "requested_stage"),
        registry=registry,
    )
    evaluation_report_exists = Gauge(
        "foehncast_training_pipeline_evaluation_report_exists",
        "Whether the latest training run produced an evaluation report.",
        labelnames=("dataset", "requested_stage"),
        registry=registry,
    )
    model_registered = Gauge(
        "foehncast_training_pipeline_model_registered",
        "Whether the latest training run registered a model version.",
        labelnames=("dataset", "requested_stage"),
        registry=registry,
    )
    registered_model_version = Gauge(
        "foehncast_training_pipeline_registered_model_version",
        "Registered model version for the latest training run when the version is numeric.",
        labelnames=("dataset", "requested_stage"),
        registry=registry,
    )
    run_metric = Gauge(
        "foehncast_training_pipeline_run_metric",
        "Logged evaluation or training metric from the latest training run.",
        labelnames=("dataset", "requested_stage", "metric_name"),
        registry=registry,
    )

    for summary in resolved_summaries:
        dataset = str(summary.get("dataset", "unknown"))
        requested_stage = str(summary.get("requested_stage", "unknown"))
        labels = (dataset, requested_stage)

        run_success.labels(*labels).set(float(summary.get("run_status") == "succeeded"))
        generated_at = summary.get("generated_at")
        if generated_at:
            summary_generated.labels(*labels).set(
                pd.Timestamp(generated_at).timestamp()
            )

        for key, gauge in (
            ("training_row_count", row_count),
            ("training_feature_count", feature_count),
            ("train_row_count", train_row_count),
            ("test_row_count", test_row_count),
        ):
            value = summary.get(key)
            if value is not None:
                gauge.labels(*labels).set(float(value))

        evaluation_report_exists.labels(*labels).set(
            float(summary.get("evaluation_report_exists", False))
        )
        model_registered.labels(*labels).set(
            float(bool(summary.get("registered_model_version")))
        )

        version = summary.get("registered_model_version")
        if version is not None and str(version).strip().isdigit():
            registered_model_version.labels(*labels).set(float(version))

        for stage, duration in dict(summary.get("stage_durations_seconds", {})).items():
            stage_duration.labels(dataset, requested_stage, str(stage)).set(
                float(duration)
            )
        for stage, count in dict(summary.get("stage_failure_counts", {})).items():
            stage_failure_count.labels(dataset, requested_stage, str(stage)).set(
                float(count)
            )
        for stage in TRAINING_PIPELINE_STAGES:
            stage_state.labels(dataset, requested_stage, stage).set(
                _stage_state_value(stage, summary)
            )
        for metric_name, value in dict(summary.get("run_metrics", {})).items():
            run_metric.labels(dataset, requested_stage, str(metric_name)).set(
                float(value)
            )

    return registry


def render_feature_pipeline_prometheus_metrics(
    summaries: list[dict[str, Any]] | None = None,
) -> bytes:
    """Return Prometheus exposition text for the latest feature-pipeline summaries."""
    registry = build_feature_pipeline_prometheus_registry(summaries=summaries)
    return generate_latest(registry)


def render_training_pipeline_prometheus_metrics(
    summaries: list[dict[str, Any]] | None = None,
) -> bytes:
    """Return Prometheus exposition text for the latest training-pipeline summaries."""
    registry = build_training_pipeline_prometheus_registry(summaries=summaries)
    return generate_latest(registry)


__all__ = [
    "CONTENT_TYPE_LATEST",
    "build_feature_pipeline_prometheus_registry",
    "build_training_pipeline_prometheus_registry",
    "render_feature_pipeline_prometheus_metrics",
    "render_training_pipeline_prometheus_metrics",
]
