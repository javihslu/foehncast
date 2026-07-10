"""Shared stage tracking helpers for typed pipeline state."""

from __future__ import annotations

from time import perf_counter
from typing import Callable, Protocol


FEATURE_PIPELINE_STAGES = ("fetch", "engineer", "validate", "store")
TRAINING_PIPELINE_STAGES = ("train", "evaluate", "register")


class SupportsStageTracking(Protocol):
    stage_durations_seconds: dict[str, float]
    stage_failure_counts: dict[str, int]


def record_stage_duration(
    state: SupportsStageTracking,
    *,
    stage: str,
    started_at: float,
    clock: Callable[[], float] = perf_counter,
) -> None:
    state.stage_durations_seconds[str(stage)] = float(clock() - started_at)


def increment_stage_failure(
    state: SupportsStageTracking,
    *,
    stage: str,
    stage_names: tuple[str, ...],
) -> None:
    counts = {
        known_stage: int(state.stage_failure_counts.get(known_stage, 0))
        for known_stage in stage_names
    }
    counts[str(stage)] = int(counts.get(str(stage), 0)) + 1
    state.stage_failure_counts = counts


__all__ = [
    "FEATURE_PIPELINE_STAGES",
    "TRAINING_PIPELINE_STAGES",
    "increment_stage_failure",
    "record_stage_duration",
]
