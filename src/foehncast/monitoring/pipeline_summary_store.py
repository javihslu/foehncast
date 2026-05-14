"""Persistence helpers for pipeline monitoring summaries."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from foehncast._json import read_json_file, write_pretty_json
from foehncast._time import compact_utc_timestamp
from foehncast.paths import project_root

ReportDirFactory = Callable[[], Path]


def _default_report_dir() -> Path:
    return project_root() / "airflow" / "reports"


def _resolve_report_dir(report_dir: ReportDirFactory | None = None) -> Path:
    return (report_dir or _default_report_dir)()


def _summary_history_dir(*, report_dir: ReportDirFactory | None = None) -> Path:
    return _resolve_report_dir(report_dir) / "history"


def _write_summary_json(path: Path, summary: dict[str, Any]) -> None:
    write_pretty_json(path, summary)


def _read_summary_json(path: Path) -> dict[str, Any]:
    return read_json_file(path)


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
    _write_summary_json(summary_path, summary)
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
    return _read_summary_json(summary_path)


def read_all_feature_pipeline_run_summaries(
    *,
    report_dir: ReportDirFactory | None = None,
) -> list[dict[str, Any]]:
    """Load all persisted feature-pipeline run summaries."""
    return [
        _read_summary_json(path)
        for path in feature_pipeline_summary_paths(report_dir=report_dir)
    ]


def read_feature_pipeline_run_summary_history(
    dataset: str | None = None,
    *,
    report_dir: ReportDirFactory | None = None,
) -> list[dict[str, Any]]:
    """Load persisted feature-pipeline run summary history."""
    return [
        _read_summary_json(path)
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
    _write_summary_json(summary_path, summary)
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
    return _read_summary_json(summary_path)


def read_all_training_pipeline_run_summaries(
    *,
    report_dir: ReportDirFactory | None = None,
) -> list[dict[str, Any]]:
    """Load all persisted training-pipeline run summaries."""
    return [
        _read_summary_json(path)
        for path in training_pipeline_summary_paths(report_dir=report_dir)
    ]


def read_training_pipeline_run_summary_history(
    dataset: str | None = None,
    *,
    report_dir: ReportDirFactory | None = None,
) -> list[dict[str, Any]]:
    """Load persisted training-pipeline run summary history."""
    return [
        _read_summary_json(path)
        for path in training_pipeline_summary_history_paths(
            dataset=dataset,
            report_dir=report_dir,
        )
    ]
def _write_summary_history(
    summary: dict[str, Any],
    *,
    prefix: str,
    dataset: str,
    report_dir: ReportDirFactory | None = None,
) -> Path:
    history_path = (
        _summary_history_dir(report_dir=report_dir)
        / f"{prefix}-{dataset}-{compact_utc_timestamp(summary.get('generated_at'))}.json"
    )
    _write_summary_json(history_path, summary)
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
