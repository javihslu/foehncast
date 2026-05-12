"""Compatibility facade for pipeline monitoring helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import mlflow

from foehncast.monitoring.pipeline_contracts import (
    FEATURE_PIPELINE_METRIC_CONTRACT,
    FEATURE_PIPELINE_STAGES,
    TRAINING_PIPELINE_METRIC_CONTRACT,
    TRAINING_PIPELINE_STAGES,
    build_feature_pipeline_run_summary,
    build_feature_pipeline_spot_summary,
    build_training_pipeline_run_summary,
    feature_pipeline_stage_overview,
    training_pipeline_stage_overview,
)
from foehncast.monitoring.pipeline_metric_export import (
    emit_feature_pipeline_run_summary as _emit_feature_pipeline_run_summary,
    emit_training_pipeline_run_summary as _emit_training_pipeline_run_summary,
    feature_pipeline_summary_metrics,
    training_pipeline_summary_metrics,
)
from foehncast.monitoring.pipeline_summary_store import (
    _default_report_dir as _store_default_report_dir,
    _summary_history_dir as _store_summary_history_dir,
    feature_pipeline_summary_history_paths as _feature_pipeline_summary_history_paths,
    feature_pipeline_summary_path as _feature_pipeline_summary_path,
    feature_pipeline_summary_paths as _feature_pipeline_summary_paths,
    read_all_feature_pipeline_run_summaries as _read_all_feature_pipeline_run_summaries,
    read_all_training_pipeline_run_summaries as _read_all_training_pipeline_run_summaries,
    read_feature_pipeline_run_summary as _read_feature_pipeline_run_summary,
    read_feature_pipeline_run_summary_history as _read_feature_pipeline_run_summary_history,
    read_training_pipeline_run_summary as _read_training_pipeline_run_summary,
    read_training_pipeline_run_summary_history as _read_training_pipeline_run_summary_history,
    training_pipeline_summary_history_paths as _training_pipeline_summary_history_paths,
    training_pipeline_summary_path as _training_pipeline_summary_path,
    training_pipeline_summary_paths as _training_pipeline_summary_paths,
    write_feature_pipeline_run_summary as _write_feature_pipeline_run_summary,
    write_training_pipeline_run_summary as _write_training_pipeline_run_summary,
)


def _default_report_dir() -> Path:
    return _store_default_report_dir()


def _summary_history_dir() -> Path:
    return _store_summary_history_dir(report_dir=_default_report_dir)


def feature_pipeline_summary_path(dataset: str = "train") -> Path:
    return _feature_pipeline_summary_path(dataset, report_dir=_default_report_dir)


def feature_pipeline_summary_paths() -> list[Path]:
    return _feature_pipeline_summary_paths(report_dir=_default_report_dir)


def feature_pipeline_summary_history_paths(dataset: str | None = None) -> list[Path]:
    return _feature_pipeline_summary_history_paths(
        dataset=dataset,
        report_dir=_default_report_dir,
    )


def training_pipeline_summary_path(dataset: str = "train") -> Path:
    return _training_pipeline_summary_path(dataset, report_dir=_default_report_dir)


def training_pipeline_summary_paths() -> list[Path]:
    return _training_pipeline_summary_paths(report_dir=_default_report_dir)


def training_pipeline_summary_history_paths(dataset: str | None = None) -> list[Path]:
    return _training_pipeline_summary_history_paths(
        dataset=dataset,
        report_dir=_default_report_dir,
    )


def write_feature_pipeline_run_summary(summary: dict[str, Any]) -> Path:
    return _write_feature_pipeline_run_summary(summary, report_dir=_default_report_dir)


def read_feature_pipeline_run_summary(dataset: str = "train") -> dict[str, Any]:
    return _read_feature_pipeline_run_summary(dataset, report_dir=_default_report_dir)


def read_all_feature_pipeline_run_summaries() -> list[dict[str, Any]]:
    return _read_all_feature_pipeline_run_summaries(report_dir=_default_report_dir)


def read_feature_pipeline_run_summary_history(
    dataset: str | None = None,
) -> list[dict[str, Any]]:
    return _read_feature_pipeline_run_summary_history(
        dataset=dataset,
        report_dir=_default_report_dir,
    )


def write_training_pipeline_run_summary(summary: dict[str, Any]) -> Path:
    return _write_training_pipeline_run_summary(summary, report_dir=_default_report_dir)


def read_training_pipeline_run_summary(dataset: str = "train") -> dict[str, Any]:
    return _read_training_pipeline_run_summary(dataset, report_dir=_default_report_dir)


def read_all_training_pipeline_run_summaries() -> list[dict[str, Any]]:
    return _read_all_training_pipeline_run_summaries(report_dir=_default_report_dir)


def read_training_pipeline_run_summary_history(
    dataset: str | None = None,
) -> list[dict[str, Any]]:
    return _read_training_pipeline_run_summary_history(
        dataset=dataset,
        report_dir=_default_report_dir,
    )


def _summary_metrics(summary: dict[str, Any]) -> dict[str, float]:
    return feature_pipeline_summary_metrics(summary)


def _training_summary_metrics(summary: dict[str, Any]) -> dict[str, float]:
    return training_pipeline_summary_metrics(summary)


def emit_feature_pipeline_run_summary(summary: dict[str, Any]) -> Path:
    """Persist the latest summary and mirror stable metrics into MLflow if active."""
    return _emit_feature_pipeline_run_summary(
        summary,
        writer=write_feature_pipeline_run_summary,
        mlflow_module=mlflow,
    )


def emit_training_pipeline_run_summary(summary: dict[str, Any]) -> Path:
    """Persist the latest summary and mirror stable training metrics into MLflow if active."""
    return _emit_training_pipeline_run_summary(
        summary,
        writer=write_training_pipeline_run_summary,
        mlflow_module=mlflow,
    )


__all__ = [
    "FEATURE_PIPELINE_STAGES",
    "FEATURE_PIPELINE_METRIC_CONTRACT",
    "TRAINING_PIPELINE_STAGES",
    "TRAINING_PIPELINE_METRIC_CONTRACT",
    "build_feature_pipeline_run_summary",
    "build_feature_pipeline_spot_summary",
    "build_training_pipeline_run_summary",
    "emit_feature_pipeline_run_summary",
    "emit_training_pipeline_run_summary",
    "feature_pipeline_summary_history_paths",
    "feature_pipeline_summary_paths",
    "feature_pipeline_stage_overview",
    "feature_pipeline_summary_path",
    "read_all_feature_pipeline_run_summaries",
    "read_feature_pipeline_run_summary_history",
    "read_all_training_pipeline_run_summaries",
    "read_feature_pipeline_run_summary",
    "read_training_pipeline_run_summary_history",
    "read_training_pipeline_run_summary",
    "training_pipeline_stage_overview",
    "training_pipeline_summary_history_paths",
    "training_pipeline_summary_path",
    "training_pipeline_summary_paths",
    "write_feature_pipeline_run_summary",
    "write_training_pipeline_run_summary",
]
