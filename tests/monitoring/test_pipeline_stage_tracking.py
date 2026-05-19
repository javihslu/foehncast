"""Tests for shared pipeline stage tracking helpers."""

from __future__ import annotations

from pathlib import Path

from foehncast.pipeline_stage_tracking import (
    FEATURE_PIPELINE_STAGES,
    TRAINING_PIPELINE_STAGES,
    increment_stage_failure,
    record_stage_duration,
)
from foehncast.pipeline_state import FeaturePipelineState, TrainingPipelineState


def test_record_stage_duration_updates_feature_state() -> None:
    state = FeaturePipelineState.new(
        dataset="train",
        run_key="manual",
        run_dir=Path("/tmp/feature-run"),
        storage_backend="bigquery",
        expected_spots=["silvaplana"],
        spot_config={"silvaplana": {"shore_orientation_deg": 225}},
    )

    record_stage_duration(
        state,
        stage="fetch",
        started_at=10.0,
        clock=lambda: 12.5,
    )

    assert state.stage_durations_seconds == {"fetch": 2.5}


def test_increment_stage_failure_preserves_known_feature_stages() -> None:
    state = FeaturePipelineState.new(
        dataset="train",
        run_key="manual",
        run_dir=Path("/tmp/feature-run"),
        storage_backend="bigquery",
        expected_spots=["silvaplana"],
        spot_config={"silvaplana": {"shore_orientation_deg": 225}},
    )
    state.stage_failure_counts["fetch"] = 1

    increment_stage_failure(
        state,
        stage="validate",
        stage_names=FEATURE_PIPELINE_STAGES,
    )

    assert state.stage_failure_counts == {
        "fetch": 1,
        "engineer": 0,
        "validate": 1,
        "store": 0,
    }


def test_increment_stage_failure_updates_training_state() -> None:
    state = TrainingPipelineState.from_summary(
        dataset="train",
        requested_stage="Candidate",
        summary={},
    )

    increment_stage_failure(
        state,
        stage="register",
        stage_names=TRAINING_PIPELINE_STAGES,
    )

    assert state.stage_failure_counts == {
        "train": 0,
        "evaluate": 0,
        "register": 1,
    }
