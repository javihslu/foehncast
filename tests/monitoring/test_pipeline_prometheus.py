"""Tests for Prometheus export of feature-pipeline summaries."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import foehncast._report_store as report_store
from foehncast.monitoring import pipeline_metrics, pipeline_prometheus
from tests.gcs_fakes import FakeStorageClient


def _metric_value(payload: str, line_prefix: str) -> float:
    for line in payload.splitlines():
        if line.startswith(line_prefix):
            return float(line.rsplit(" ", 1)[1])
    raise AssertionError(f"metric line not found: {line_prefix}")


def test_render_feature_pipeline_prometheus_metrics_uses_labelled_gauges(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(pipeline_metrics, "_default_report_dir", lambda: tmp_path)
    pipeline_metrics.write_feature_pipeline_run_summary(
        {
            "contract_version": 1,
            "generated_at": "2026-05-05T10:15:00+00:00",
            "run_status": "succeeded",
            "dataset": "train",
            "storage_backend": "s3",
            "expected_spot_count": 2,
            "fetched_spot_count": 2,
            "engineered_spot_count": 2,
            "validated_spot_count": 2,
            "stored_spot_count": 2,
            "drifted_spot_count": 1,
            "dataset_drift_detected": True,
            "feature_persistence_ready": True,
            "training_handoff_mode": "drift",
            "training_handoff_state": "ready",
            "training_handoff_ready": True,
            "training_request_stage": "Production",
            "training_request_asset_uri": "x-foehncast://airflow/training-request/train/production",
            "stage_durations_seconds": {"fetch": 12.5, "store": 3.5},
            "stage_failure_counts": {
                "fetch": 0,
                "engineer": 0,
                "validate": 0,
                "store": 0,
            },
            "skipped_spot_count": 0,
            "failed_spot_count": 0,
            "spots": [
                {
                    "spot_id": "silvaplana",
                    "ingest": {"rows": 168},
                    "engineering": {"rows": 168, "engineered_column_count": 7},
                    "validation": {"is_valid": True, "range_violation_count": 0},
                    "storage": {
                        "stored_rows": 168,
                        "max_numeric_abs_delta": 0.0,
                        "time_basis_preserved": True,
                    },
                    "feast": {"projection_ready": True},
                }
            ],
        }
    )

    payload = pipeline_prometheus.render_feature_pipeline_prometheus_metrics().decode(
        "utf-8"
    )

    assert "foehncast_feature_pipeline_summary_count 1.0" in payload
    assert (
        'foehncast_feature_pipeline_run_success{dataset="train",storage_backend="s3"} 1.0'
        in payload
    )
    assert (
        'foehncast_feature_pipeline_spot_ingest_rows{dataset="train",spot_id="silvaplana",storage_backend="s3"} 168.0'
        in payload
    )
    assert (
        'foehncast_feature_pipeline_engineered_spot_count{dataset="train",storage_backend="s3"} 2.0'
        in payload
    )
    assert (
        'foehncast_feature_pipeline_validated_spot_count{dataset="train",storage_backend="s3"} 2.0'
        in payload
    )
    assert (
        'foehncast_feature_pipeline_stage_duration_seconds{dataset="train",stage="fetch",storage_backend="s3"} 12.5'
        in payload
    )
    assert (
        'foehncast_feature_pipeline_stage_failure_count{dataset="train",stage="fetch",storage_backend="s3"} 0.0'
        in payload
    )
    assert (
        'foehncast_feature_pipeline_spot_feast_projection_ready{dataset="train",spot_id="silvaplana",storage_backend="s3"} 1.0'
        in payload
    )
    assert (
        'foehncast_feature_pipeline_drifted_spot_count{dataset="train",storage_backend="s3"} 1.0'
        in payload
    )
    assert (
        'foehncast_feature_pipeline_dataset_drift_detected{dataset="train",storage_backend="s3"} 1.0'
        in payload
    )
    assert (
        'foehncast_feature_pipeline_feature_persistence_ready{dataset="train",storage_backend="s3"} 1.0'
        in payload
    )
    assert (
        'foehncast_feature_pipeline_training_handoff_ready{dataset="train",storage_backend="s3"} 1.0'
        in payload
    )
    # A summary without a recorded materialization renders no freshness sample.
    assert 'foehncast_feast_max_feature_age_seconds{dataset="train"}' not in payload


def test_feast_materialize_age_seconds_parses_clamps_and_guards() -> None:
    now = pd.Timestamp("2026-05-12T16:00:00+00:00")

    assert (
        pipeline_prometheus._feast_materialize_age_seconds(
            "2026-05-12T13:00:00+00:00", now=now
        )
        == 10800.0
    )
    # A naive timestamp is read as UTC.
    assert (
        pipeline_prometheus._feast_materialize_age_seconds(
            "2026-05-12T13:00:00", now=now
        )
        == 10800.0
    )
    # A future timestamp (clock skew) clamps to zero.
    assert (
        pipeline_prometheus._feast_materialize_age_seconds(
            "2026-05-12T17:00:00+00:00", now=now
        )
        == 0.0
    )
    # Missing or unparseable values render no gauge.
    assert pipeline_prometheus._feast_materialize_age_seconds(None, now=now) is None
    assert pipeline_prometheus._feast_materialize_age_seconds("", now=now) is None
    assert (
        pipeline_prometheus._feast_materialize_age_seconds("not-a-date", now=now)
        is None
    )


def test_render_feature_pipeline_prometheus_metrics_emits_feast_feature_age(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(pipeline_metrics, "_default_report_dir", lambda: tmp_path)
    materialized_at = pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=3)
    pipeline_metrics.write_feature_pipeline_run_summary(
        {
            "contract_version": 1,
            "generated_at": "2026-05-12T12:00:00+00:00",
            "run_status": "succeeded",
            "dataset": "train",
            "storage_backend": "s3",
            "feast_materialize_timestamp": materialized_at.isoformat(),
        }
    )

    payload = pipeline_prometheus.render_feature_pipeline_prometheus_metrics().decode(
        "utf-8"
    )

    prefix = 'foehncast_feast_max_feature_age_seconds{dataset="train"} '
    assert prefix in payload
    assert abs(_metric_value(payload, prefix) - 10800.0) < 120.0


def test_render_training_pipeline_prometheus_metrics_uses_labelled_gauges(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(pipeline_metrics, "_default_report_dir", lambda: tmp_path)
    pipeline_metrics.write_training_pipeline_run_summary(
        {
            "contract_version": 1,
            "generated_at": "2026-05-12T13:30:00+00:00",
            "run_status": "succeeded",
            "dataset": "train",
            "requested_stage": "Production",
            "training_run_id": "run-123",
            "training_row_count": 240,
            "training_feature_count": 18,
            "train_row_count": 180,
            "test_row_count": 60,
            "evaluation_report_exists": True,
            "registered_model_version": "7",
            "stage_states": {
                "train": "succeeded",
                "evaluate": "succeeded",
                "register": "succeeded",
            },
            "stage_durations_seconds": {"train": 12.5, "evaluate": 1.5},
            "stage_failure_counts": {"train": 0, "evaluate": 0, "register": 0},
            "run_metrics": {"mae": 0.4, "r2": 0.82},
        }
    )

    payload = pipeline_prometheus.render_training_pipeline_prometheus_metrics().decode(
        "utf-8"
    )

    assert "foehncast_training_pipeline_summary_count 1.0" in payload
    assert (
        'foehncast_training_pipeline_run_success{dataset="train",requested_stage="Production"} 1.0'
        in payload
    )
    assert (
        'foehncast_training_pipeline_stage_duration_seconds{dataset="train",requested_stage="Production",stage="train"} 12.5'
        in payload
    )
    assert (
        'foehncast_training_pipeline_stage_state{dataset="train",requested_stage="Production",stage="register"} 1.0'
        in payload
    )
    assert (
        'foehncast_training_pipeline_row_count{dataset="train",requested_stage="Production"} 240.0'
        in payload
    )
    assert (
        'foehncast_training_pipeline_run_metric{dataset="train",metric_name="mae",requested_stage="Production"} 0.4'
        in payload
    )


def test_render_feature_pipeline_prometheus_metrics_reads_gcs_backed_summaries(
    monkeypatch,
) -> None:
    fake_storage = FakeStorageClient()

    monkeypatch.setattr(report_store, "_new_storage_client", lambda: fake_storage)
    monkeypatch.setenv(
        "FOEHNCAST_PIPELINE_REPORT_DIR",
        "gs://demo-bucket/airflow/reports",
    )

    pipeline_metrics.write_feature_pipeline_run_summary(
        {
            "contract_version": 1,
            "generated_at": "2026-05-16T15:00:00+00:00",
            "run_status": "succeeded",
            "dataset": "train",
            "storage_backend": "bigquery",
            "expected_spot_count": 1,
            "fetched_spot_count": 1,
            "engineered_spot_count": 1,
            "validated_spot_count": 1,
            "stored_spot_count": 1,
            "drifted_spot_count": 0,
            "dataset_drift_detected": False,
            "feature_persistence_ready": True,
            "training_handoff_mode": "always",
            "training_handoff_state": "ready",
            "training_handoff_ready": True,
            "training_request_stage": "Production",
            "training_request_asset_uri": "x-foehncast://airflow/training-request/train/production",
            "stage_durations_seconds": {"fetch": 8.0},
            "stage_failure_counts": {
                "fetch": 0,
                "engineer": 0,
                "validate": 0,
                "store": 0,
            },
            "skipped_spot_count": 0,
            "failed_spot_count": 0,
            "spots": [
                {
                    "spot_id": "silvaplana",
                    "ingest": {"rows": 24},
                    "engineering": {"rows": 24, "engineered_column_count": 7},
                    "validation": {"is_valid": True, "range_violation_count": 0},
                    "storage": {
                        "stored_rows": 24,
                        "max_numeric_abs_delta": 0.0,
                        "time_basis_preserved": True,
                    },
                    "feast": {"projection_ready": True},
                }
            ],
        }
    )

    payload = pipeline_prometheus.render_feature_pipeline_prometheus_metrics().decode(
        "utf-8"
    )

    assert (
        json.loads(
            fake_storage.objects[
                ("demo-bucket", "airflow/reports/feature-pipeline-train-latest.json")
            ]
        )["dataset"]
        == "train"
    )
    assert "foehncast_feature_pipeline_summary_count 1.0" in payload
    assert (
        'foehncast_feature_pipeline_run_success{dataset="train",storage_backend="bigquery"} 1.0'
        in payload
    )
    assert (
        'foehncast_feature_pipeline_training_handoff_ready{dataset="train",storage_backend="bigquery"} 1.0'
        in payload
    )
