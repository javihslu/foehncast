"""Typed orchestration state for feature and training pipelines."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from foehncast.pipeline_stage_tracking import (
    FEATURE_PIPELINE_STAGES,
    TRAINING_PIPELINE_STAGES,
)


def _string_list(values: object) -> list[str]:
    return [str(value) for value in list(values or [])]


def _float_mapping(values: object) -> dict[str, float]:
    return {str(name): float(value) for name, value in dict(values or {}).items()}


def _int_mapping(values: object, *, stages: tuple[str, ...]) -> dict[str, int]:
    resolved = {str(name): int(value) for name, value in dict(values or {}).items()}
    return {stage: int(resolved.get(stage, 0)) for stage in stages}


def _string_mapping(values: object) -> dict[str, str]:
    return {str(name): str(value) for name, value in dict(values or {}).items()}


def _spot_config_mapping(values: object) -> dict[str, dict[str, object]]:
    return {
        str(spot_id): dict(config) for spot_id, config in dict(values or {}).items()
    }


def _int_or_none(value: object) -> int | None:
    return None if value is None else int(value)


def _string_or_none(value: object) -> str | None:
    return None if value is None else str(value)


@dataclass(slots=True)
class FeaturePipelineState:
    dataset: str
    run_key: str
    run_dir: Path
    storage_backend: str
    expected_spots: list[str] = field(default_factory=list)
    fetched_spots: list[str] = field(default_factory=list)
    engineered_spots: list[str] = field(default_factory=list)
    validated_spots: list[str] = field(default_factory=list)
    stored_spots: list[str] = field(default_factory=list)
    drifted_spots: list[str] = field(default_factory=list)
    stage_durations_seconds: dict[str, float] = field(default_factory=dict)
    stage_failure_counts: dict[str, int] = field(
        default_factory=lambda: {stage: 0 for stage in FEATURE_PIPELINE_STAGES}
    )
    spot_errors: dict[str, str] = field(default_factory=dict)
    spot_config: dict[str, dict[str, object]] = field(default_factory=dict)

    @classmethod
    def new(
        cls,
        *,
        dataset: str,
        run_key: str,
        run_dir: Path,
        storage_backend: str,
        expected_spots: list[str],
        spot_config: dict[str, dict[str, object]],
    ) -> FeaturePipelineState:
        return cls(
            dataset=dataset,
            run_key=run_key,
            run_dir=run_dir,
            storage_backend=storage_backend,
            expected_spots=list(expected_spots),
            stage_failure_counts={stage: 0 for stage in FEATURE_PIPELINE_STAGES},
            spot_config={
                spot_id: dict(config) for spot_id, config in spot_config.items()
            },
        )

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, object],
    ) -> FeaturePipelineState:
        return cls(
            dataset=str(payload.get("dataset", "train")),
            run_key=str(payload.get("run_key", "manual")),
            run_dir=Path(str(payload.get("run_dir", "."))),
            storage_backend=str(payload.get("storage_backend", "")),
            expected_spots=_string_list(payload.get("expected_spots", [])),
            fetched_spots=_string_list(payload.get("fetched_spots", [])),
            engineered_spots=_string_list(payload.get("engineered_spots", [])),
            validated_spots=_string_list(payload.get("validated_spots", [])),
            stored_spots=_string_list(payload.get("stored_spots", [])),
            drifted_spots=_string_list(payload.get("drifted_spots", [])),
            stage_durations_seconds=_float_mapping(
                payload.get("stage_durations_seconds", {})
            ),
            stage_failure_counts=_int_mapping(
                payload.get("stage_failure_counts", {}),
                stages=FEATURE_PIPELINE_STAGES,
            ),
            spot_errors=_string_mapping(payload.get("spot_errors", {})),
            spot_config=_spot_config_mapping(payload.get("spot_config", {})),
        )

    def copy(self) -> FeaturePipelineState:
        return FeaturePipelineState(
            dataset=self.dataset,
            run_key=self.run_key,
            run_dir=self.run_dir,
            storage_backend=self.storage_backend,
            expected_spots=list(self.expected_spots),
            fetched_spots=list(self.fetched_spots),
            engineered_spots=list(self.engineered_spots),
            validated_spots=list(self.validated_spots),
            stored_spots=list(self.stored_spots),
            drifted_spots=list(self.drifted_spots),
            stage_durations_seconds=dict(self.stage_durations_seconds),
            stage_failure_counts=dict(self.stage_failure_counts),
            spot_errors=dict(self.spot_errors),
            spot_config={
                spot_id: dict(config) for spot_id, config in self.spot_config.items()
            },
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "dataset": self.dataset,
            "run_key": self.run_key,
            "run_dir": str(self.run_dir),
            "storage_backend": self.storage_backend,
            "expected_spots": list(self.expected_spots),
            "fetched_spots": list(self.fetched_spots),
            "engineered_spots": list(self.engineered_spots),
            "validated_spots": list(self.validated_spots),
            "stored_spots": list(self.stored_spots),
            "drifted_spots": list(self.drifted_spots),
            "stage_durations_seconds": dict(self.stage_durations_seconds),
            "stage_failure_counts": dict(self.stage_failure_counts),
            "spot_errors": dict(self.spot_errors),
            "spot_config": {
                spot_id: dict(config) for spot_id, config in self.spot_config.items()
            },
        }


@dataclass(slots=True)
class TrainingPipelineState:
    dataset: str
    requested_stage: str
    training_run_id: str | None = None
    stage_durations_seconds: dict[str, float] = field(default_factory=dict)
    stage_failure_counts: dict[str, int] = field(
        default_factory=lambda: {stage: 0 for stage in TRAINING_PIPELINE_STAGES}
    )
    training_row_count: int | None = None
    training_feature_count: int | None = None
    train_row_count: int | None = None
    test_row_count: int | None = None
    evaluation_report_path: str | None = None
    evaluation_report_exists: bool = False
    registered_model_name: str | None = None
    registered_model_version: str | None = None
    run_metrics: dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_summary(
        cls,
        *,
        dataset: str,
        requested_stage: str,
        summary: Mapping[str, Any],
        training_run_id: str | None = None,
    ) -> TrainingPipelineState:
        resolved_summary: Mapping[str, Any] = summary
        if training_run_id and summary.get("training_run_id") not in {
            None,
            training_run_id,
        }:
            resolved_summary = {}

        return cls(
            dataset=dataset,
            requested_stage=requested_stage,
            training_run_id=training_run_id
            or _string_or_none(resolved_summary.get("training_run_id")),
            stage_durations_seconds=_float_mapping(
                resolved_summary.get("stage_durations_seconds", {})
            ),
            stage_failure_counts=_int_mapping(
                resolved_summary.get("stage_failure_counts", {}),
                stages=TRAINING_PIPELINE_STAGES,
            ),
            training_row_count=_int_or_none(resolved_summary.get("training_row_count")),
            training_feature_count=_int_or_none(
                resolved_summary.get("training_feature_count")
            ),
            train_row_count=_int_or_none(resolved_summary.get("train_row_count")),
            test_row_count=_int_or_none(resolved_summary.get("test_row_count")),
            evaluation_report_path=_string_or_none(
                resolved_summary.get("evaluation_report_path")
            ),
            evaluation_report_exists=bool(
                resolved_summary.get("evaluation_report_exists", False)
            ),
            registered_model_name=_string_or_none(
                resolved_summary.get("registered_model_name")
            ),
            registered_model_version=_string_or_none(
                resolved_summary.get("registered_model_version")
            ),
            run_metrics=_float_mapping(resolved_summary.get("run_metrics", {})),
        )

    def merge_run_snapshot(self, snapshot: Mapping[str, Any]) -> None:
        if "run_metrics" in snapshot:
            self.run_metrics = _float_mapping(snapshot.get("run_metrics", {}))
        if "training_row_count" in snapshot:
            self.training_row_count = _int_or_none(snapshot.get("training_row_count"))
        if "training_feature_count" in snapshot:
            self.training_feature_count = _int_or_none(
                snapshot.get("training_feature_count")
            )
        if "train_row_count" in snapshot:
            self.train_row_count = _int_or_none(snapshot.get("train_row_count"))
        if "test_row_count" in snapshot:
            self.test_row_count = _int_or_none(snapshot.get("test_row_count"))
        if "registered_model_name" in snapshot:
            self.registered_model_name = _string_or_none(
                snapshot.get("registered_model_name")
            )

    def to_summary_payload(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "requested_stage": self.requested_stage,
            "training_run_id": self.training_run_id,
            "stage_durations_seconds": dict(self.stage_durations_seconds),
            "stage_failure_counts": dict(self.stage_failure_counts),
            "run_metrics": dict(self.run_metrics),
            "training_row_count": self.training_row_count,
            "training_feature_count": self.training_feature_count,
            "train_row_count": self.train_row_count,
            "test_row_count": self.test_row_count,
            "evaluation_report_path": self.evaluation_report_path,
            "evaluation_report_exists": self.evaluation_report_exists,
            "registered_model_name": self.registered_model_name,
            "registered_model_version": self.registered_model_version,
        }


__all__ = ["FeaturePipelineState", "TrainingPipelineState"]
