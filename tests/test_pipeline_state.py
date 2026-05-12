"""Tests for typed pipeline orchestration state."""

from __future__ import annotations

from pathlib import Path

from foehncast.pipeline_state import FeaturePipelineState, TrainingPipelineState


def test_feature_pipeline_state_round_trips_airflow_payload() -> None:
    state = FeaturePipelineState.from_payload(
        {
            "dataset": "train",
            "run_key": "manual-123",
            "run_dir": "/tmp/feature-run",
            "storage_backend": "bigquery",
            "expected_spots": ["silvaplana", "urnersee"],
            "fetched_spots": ["silvaplana"],
            "stage_durations_seconds": {"fetch": 1.5},
            "stage_failure_counts": {"fetch": 1},
            "spot_errors": {"urnersee": "missing rows"},
            "spot_config": {
                "silvaplana": {"shore_orientation_deg": 225},
            },
        }
    )

    assert state.run_dir == Path("/tmp/feature-run")
    assert state.stage_failure_counts["fetch"] == 1
    assert state.stage_failure_counts["engineer"] == 0
    assert state.spot_errors == {"urnersee": "missing rows"}
    assert state.to_payload()["run_dir"] == "/tmp/feature-run"


def test_training_pipeline_state_from_summary_normalizes_fields() -> None:
    state = TrainingPipelineState.from_summary(
        dataset="train",
        requested_stage="Candidate",
        summary={
            "training_run_id": "run-123",
            "stage_durations_seconds": {"train": 8.5},
            "stage_failure_counts": {"train": 1},
            "training_row_count": 240.0,
            "training_feature_count": 18.0,
            "train_row_count": 180.0,
            "test_row_count": 60.0,
            "evaluation_report_exists": 1,
            "registered_model_version": 7,
            "run_metrics": {"mae": 0.5},
        },
    )

    assert state.training_run_id == "run-123"
    assert state.training_row_count == 240
    assert state.training_feature_count == 18
    assert state.stage_failure_counts["train"] == 1
    assert state.stage_failure_counts["evaluate"] == 0
    assert state.registered_model_version == "7"
    assert state.run_metrics == {"mae": 0.5}


def test_training_pipeline_state_ignores_mismatched_summary_run() -> None:
    state = TrainingPipelineState.from_summary(
        dataset="train",
        requested_stage="Candidate",
        training_run_id="run-456",
        summary={
            "training_run_id": "run-123",
            "training_row_count": 240,
            "run_metrics": {"mae": 0.5},
        },
    )

    assert state.training_run_id == "run-456"
    assert state.training_row_count is None
    assert state.run_metrics == {}


def test_training_pipeline_state_merges_run_snapshot() -> None:
    state = TrainingPipelineState.from_summary(
        dataset="train",
        requested_stage="Candidate",
        summary={},
    )

    state.merge_run_snapshot(
        {
            "run_metrics": {"mae": 0.5},
            "training_row_count": 240,
            "training_feature_count": 18,
            "train_row_count": 180,
            "test_row_count": 60,
            "registered_model_name": "foehncast",
        }
    )

    assert state.run_metrics == {"mae": 0.5}
    assert state.training_row_count == 240
    assert state.training_feature_count == 18
    assert state.train_row_count == 180
    assert state.test_row_count == 60
    assert state.registered_model_name == "foehncast"
