"""Persistence helpers for pipeline monitoring summaries."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from foehncast.paths import project_root

ReportDirFactory = Callable[[], Path]


def _default_report_dir() -> Path:
    return project_root() / "airflow" / "reports"


def _resolve_report_dir(report_dir: ReportDirFactory | None = None) -> Path:
    return (report_dir or _default_report_dir)()


def _summary_history_dir(*, report_dir: ReportDirFactory | None = None) -> Path:
    return _resolve_report_dir(report_dir) / "history"


def feature_pipeline_summary_path(
    dataset: str = "train",
    *,
    report_dir: ReportDirFactory | None = None,
) -> Path:
    """Return the stable JSON summary path for the latest feature pipeline run."""
    return _resolve_report_dir(report_dir) / f"feature-pipeline-{dataset}-latest.json"


def feature_pipeline_summary_paths(
    *,
    report_dir: ReportDirFactory | None = None,
) -> list[Path]:
    """Return all persisted feature-pipeline summary paths."""
    return sorted(
        _resolve_report_dir(report_dir).glob("feature-pipeline-*-latest.json")
    )


def feature_pipeline_summary_history_paths(
    dataset: str | None = None,
    *,
    report_dir: ReportDirFactory | None = None,
) -> list[Path]:
    """Return persisted feature-pipeline summary history paths."""
    pattern = "feature-pipeline-*.json"
    if dataset is not None:
        pattern = f"feature-pipeline-{dataset}-*.json"
    return sorted(_summary_history_dir(report_dir=report_dir).glob(pattern))


def training_pipeline_summary_path(
    dataset: str = "train",
    *,
    report_dir: ReportDirFactory | None = None,
) -> Path:
    """Return the stable JSON summary path for the latest training pipeline run."""
    return _resolve_report_dir(report_dir) / f"training-pipeline-{dataset}-latest.json"


def training_pipeline_summary_paths(
    *,
    report_dir: ReportDirFactory | None = None,
) -> list[Path]:
    """Return all persisted training-pipeline summary paths."""
    return sorted(
        _resolve_report_dir(report_dir).glob("training-pipeline-*-latest.json")
    )


def training_pipeline_summary_history_paths(
    dataset: str | None = None,
    *,
    report_dir: ReportDirFactory | None = None,
) -> list[Path]:
    """Return persisted training-pipeline summary history paths."""
    pattern = "training-pipeline-*.json"
    if dataset is not None:
        pattern = f"training-pipeline-{dataset}-*.json"
    return sorted(_summary_history_dir(report_dir=report_dir).glob(pattern))


def write_feature_pipeline_run_summary(
    summary: dict[str, Any],
    *,
    report_dir: ReportDirFactory | None = None,
) -> Path:
    """Persist the latest run summary to a stable JSON file."""
    summary_path = feature_pipeline_summary_path(
        str(summary["dataset"]), report_dir=report_dir
    )
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    _write_summary_history(
        summary,
        prefix="feature-pipeline",
        dataset=str(summary["dataset"]),
        report_dir=report_dir,
    )
    return summary_path


def read_feature_pipeline_run_summary(
    dataset: str = "train",
    *,
    report_dir: ReportDirFactory | None = None,
) -> dict[str, Any]:
    """Load the latest persisted feature-pipeline run summary."""
    summary_path = feature_pipeline_summary_path(dataset, report_dir=report_dir)
    return json.loads(summary_path.read_text())


def read_all_feature_pipeline_run_summaries(
    *,
    report_dir: ReportDirFactory | None = None,
) -> list[dict[str, Any]]:
    """Load all persisted feature-pipeline run summaries."""
    return [
        json.loads(path.read_text())
        for path in feature_pipeline_summary_paths(report_dir=report_dir)
    ]


def read_feature_pipeline_run_summary_history(
    dataset: str | None = None,
    *,
    report_dir: ReportDirFactory | None = None,
) -> list[dict[str, Any]]:
    """Load persisted feature-pipeline run summary history."""
    return [
        json.loads(path.read_text())
        for path in feature_pipeline_summary_history_paths(
            dataset=dataset,
            report_dir=report_dir,
        )
    ]


def write_training_pipeline_run_summary(
    summary: dict[str, Any],
    *,
    report_dir: ReportDirFactory | None = None,
) -> Path:
    """Persist the latest training run summary to a stable JSON file."""
    summary_path = training_pipeline_summary_path(
        str(summary["dataset"]), report_dir=report_dir
    )
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    _write_summary_history(
        summary,
        prefix="training-pipeline",
        dataset=str(summary["dataset"]),
        report_dir=report_dir,
    )
    return summary_path


def read_training_pipeline_run_summary(
    dataset: str = "train",
    *,
    report_dir: ReportDirFactory | None = None,
) -> dict[str, Any]:
    """Load the latest persisted training-pipeline run summary."""
    summary_path = training_pipeline_summary_path(dataset, report_dir=report_dir)
    return json.loads(summary_path.read_text())


def read_all_training_pipeline_run_summaries(
    *,
    report_dir: ReportDirFactory | None = None,
) -> list[dict[str, Any]]:
    """Load all persisted training-pipeline run summaries."""
    return [
        json.loads(path.read_text())
        for path in training_pipeline_summary_paths(report_dir=report_dir)
    ]


def read_training_pipeline_run_summary_history(
    dataset: str | None = None,
    *,
    report_dir: ReportDirFactory | None = None,
) -> list[dict[str, Any]]:
    """Load persisted training-pipeline run summary history."""
    return [
        json.loads(path.read_text())
        for path in training_pipeline_summary_history_paths(
            dataset=dataset,
            report_dir=report_dir,
        )
    ]


def _summary_history_timestamp(summary: dict[str, Any]) -> str:
    raw_timestamp = summary.get("generated_at")
    try:
        timestamp = pd.Timestamp(raw_timestamp)
    except (TypeError, ValueError):
        timestamp = pd.Timestamp(datetime.now(tz=UTC))

    if pd.isna(timestamp):
        timestamp = pd.Timestamp(datetime.now(tz=UTC))

    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize(UTC)
    else:
        timestamp = timestamp.tz_convert(UTC)

    return timestamp.strftime("%Y%m%dT%H%M%S%fZ")


def _write_summary_history(
    summary: dict[str, Any],
    *,
    prefix: str,
    dataset: str,
    report_dir: ReportDirFactory | None = None,
) -> Path:
    history_path = (
        _summary_history_dir(report_dir=report_dir)
        / f"{prefix}-{dataset}-{_summary_history_timestamp(summary)}.json"
    )
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return history_path


__all__ = [
    "feature_pipeline_summary_history_paths",
    "feature_pipeline_summary_path",
    "feature_pipeline_summary_paths",
    "read_all_feature_pipeline_run_summaries",
    "read_all_training_pipeline_run_summaries",
    "read_feature_pipeline_run_summary",
    "read_feature_pipeline_run_summary_history",
    "read_training_pipeline_run_summary",
    "read_training_pipeline_run_summary_history",
    "training_pipeline_summary_history_paths",
    "training_pipeline_summary_path",
    "training_pipeline_summary_paths",
    "write_feature_pipeline_run_summary",
    "write_training_pipeline_run_summary",
]
