"""Tests for Prometheus export of feature-pipeline summaries."""

from __future__ import annotations

from pathlib import Path

from foehncast.monitoring import pipeline_metrics, pipeline_prometheus


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
