"""Public helpers for pipeline summary persistence and export."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import mlflow

from foehncast._json import read_json_file, write_pretty_json
from foehncast._time import compact_utc_timestamp
from foehncast.monitoring._common import registered_model_version_metric_value
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
    return _resolve_report_dir(report_dir) / f"feature-pipeline-{dataset}-latest.json"


def feature_pipeline_summary_paths(
    *,
    report_dir: ReportDirFactory | None = None,
) -> list[Path]:
    return sorted(
        _resolve_report_dir(report_dir).glob("feature-pipeline-*-latest.json")
    )


def feature_pipeline_summary_history_paths(
    dataset: str | None = None,
    *,
    report_dir: ReportDirFactory | None = None,
) -> list[Path]:
    pattern = "feature-pipeline-*.json"
    if dataset is not None:
        pattern = f"feature-pipeline-{dataset}-*.json"
    return sorted(_summary_history_dir(report_dir=report_dir).glob(pattern))


def training_pipeline_summary_path(
    dataset: str = "train",
    *,
    report_dir: ReportDirFactory | None = None,
) -> Path:
    return _resolve_report_dir(report_dir) / f"training-pipeline-{dataset}-latest.json"


def training_pipeline_summary_paths(
    *,
    report_dir: ReportDirFactory | None = None,
) -> list[Path]:
    return sorted(
        _resolve_report_dir(report_dir).glob("training-pipeline-*-latest.json")
    )


def training_pipeline_summary_history_paths(
    dataset: str | None = None,
    *,
    report_dir: ReportDirFactory | None = None,
) -> list[Path]:
    pattern = "training-pipeline-*.json"
    if dataset is not None:
        pattern = f"training-pipeline-{dataset}-*.json"
    return sorted(_summary_history_dir(report_dir=report_dir).glob(pattern))


def write_feature_pipeline_run_summary(
    summary: dict[str, Any],
    *,
    report_dir: ReportDirFactory | None = None,
) -> Path:
    summary_path = feature_pipeline_summary_path(
        str(summary["dataset"]),
        report_dir=report_dir,
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
    summary_path = feature_pipeline_summary_path(dataset, report_dir=report_dir)
    return _read_summary_json(summary_path)


def read_all_feature_pipeline_run_summaries(
    *,
    report_dir: ReportDirFactory | None = None,
) -> list[dict[str, Any]]:
    return [
        _read_summary_json(path)
        for path in feature_pipeline_summary_paths(report_dir=report_dir)
    ]


def read_feature_pipeline_run_summary_history(
    dataset: str | None = None,
    *,
    report_dir: ReportDirFactory | None = None,
) -> list[dict[str, Any]]:
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
    summary_path = training_pipeline_summary_path(
        str(summary["dataset"]),
        report_dir=report_dir,
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
    summary_path = training_pipeline_summary_path(dataset, report_dir=report_dir)
    return _read_summary_json(summary_path)


def read_all_training_pipeline_run_summaries(
    *,
    report_dir: ReportDirFactory | None = None,
) -> list[dict[str, Any]]:
    return [
        _read_summary_json(path)
        for path in training_pipeline_summary_paths(report_dir=report_dir)
    ]


def read_training_pipeline_run_summary_history(
    dataset: str | None = None,
    *,
    report_dir: ReportDirFactory | None = None,
) -> list[dict[str, Any]]:
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


def feature_pipeline_summary_metrics(summary: dict[str, Any]) -> dict[str, float]:
    metrics = {
        "feature_expected_spot_count": float(summary["expected_spot_count"]),
        "feature_fetched_spot_count": float(summary["fetched_spot_count"]),
        "feature_engineered_spot_count": float(summary["engineered_spot_count"]),
        "feature_validated_spot_count": float(summary["validated_spot_count"]),
        "feature_stored_spot_count": float(summary["stored_spot_count"]),
        "feature_skipped_spot_count": float(summary["skipped_spot_count"]),
        "feature_failed_spot_count": float(summary["failed_spot_count"]),
    }

    for stage, duration in dict(summary.get("stage_durations_seconds", {})).items():
        metrics[f"feature_{stage}_duration_seconds"] = float(duration)

    for stage, count in dict(summary.get("stage_failure_counts", {})).items():
        metrics[f"feature_{stage}_failure_count"] = float(count)

    for spot_summary in summary.get("spots", []):
        prefix = f"feature_{spot_summary['spot_id']}"
        metrics[f"{prefix}_ingest_rows"] = float(spot_summary["ingest"]["rows"])
        metrics[f"{prefix}_source_unit_contract_confirmed"] = float(
            spot_summary["ingest"].get("source_unit_contract_confirmed", False)
        )
        metrics[f"{prefix}_engineered_rows"] = float(
            spot_summary["engineering"]["rows"]
        )
        metrics[f"{prefix}_validation_passed"] = float(
            spot_summary["validation"]["is_valid"]
        )
        metrics[f"{prefix}_range_violation_count"] = float(
            spot_summary["validation"]["range_violation_count"]
        )
        metrics[f"{prefix}_stored_rows"] = float(spot_summary["storage"]["stored_rows"])
        max_delta = spot_summary["storage"]["max_numeric_abs_delta"]
        if max_delta is not None:
            metrics[f"{prefix}_max_numeric_abs_delta"] = float(max_delta)
        metrics[f"{prefix}_feast_projection_ready"] = float(
            spot_summary["feast"]["projection_ready"]
        )

    return metrics


def training_pipeline_summary_metrics(summary: dict[str, Any]) -> dict[str, float]:
    metrics: dict[str, float] = {}

    for key, metric_name in (
        ("training_row_count", "training_row_count"),
        ("training_feature_count", "training_feature_count"),
        ("train_row_count", "training_train_row_count"),
        ("test_row_count", "training_test_row_count"),
    ):
        value = summary.get(key)
        if value is not None:
            metrics[metric_name] = float(value)

    metrics["training_evaluation_report_exists"] = float(
        summary.get("evaluation_report_exists", False)
    )
    metrics["training_model_registered"] = float(
        bool(summary.get("registered_model_version"))
    )

    version = summary.get("registered_model_version")
    numeric_version = registered_model_version_metric_value(version)
    if numeric_version is not None:
        metrics["training_registered_model_version"] = numeric_version

    for stage, duration in dict(summary.get("stage_durations_seconds", {})).items():
        metrics[f"training_{stage}_duration_seconds"] = float(duration)

    for stage, count in dict(summary.get("stage_failure_counts", {})).items():
        metrics[f"training_{stage}_failure_count"] = float(count)

    for name, value in dict(summary.get("run_metrics", {})).items():
        metrics[f"training_metric_{name}"] = float(value)

    return metrics


def _emit_summary(
    summary: dict[str, Any],
    *,
    writer: Callable[[dict[str, Any]], Path],
    metrics_builder: Callable[[dict[str, Any]], dict[str, float]],
    artifact_path: str,
    mlflow_module: Any,
) -> Path:
    summary_path = writer(summary)
    active_run = getattr(mlflow_module, "active_run", lambda: None)()
    if active_run is None:
        return summary_path

    mlflow_module.log_metrics(metrics_builder(summary))
    mlflow_module.log_artifact(str(summary_path), artifact_path=artifact_path)
    return summary_path


def emit_feature_pipeline_run_summary(summary: dict[str, Any]) -> Path:
    """Persist the latest summary and mirror stable metrics into MLflow if active."""
    return _emit_summary(
        summary,
        writer=write_feature_pipeline_run_summary,
        metrics_builder=feature_pipeline_summary_metrics,
        artifact_path="monitoring/feature_pipeline",
        mlflow_module=mlflow,
    )


def emit_training_pipeline_run_summary(summary: dict[str, Any]) -> Path:
    """Persist the latest summary and mirror stable training metrics into MLflow if active."""
    return _emit_summary(
        summary,
        writer=write_training_pipeline_run_summary,
        metrics_builder=training_pipeline_summary_metrics,
        artifact_path="monitoring/training_pipeline",
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
    "feature_pipeline_summary_metrics",
    "read_all_feature_pipeline_run_summaries",
    "read_feature_pipeline_run_summary_history",
    "read_all_training_pipeline_run_summaries",
    "read_feature_pipeline_run_summary",
    "read_training_pipeline_run_summary_history",
    "read_training_pipeline_run_summary",
    "training_pipeline_summary_metrics",
    "training_pipeline_stage_overview",
    "training_pipeline_summary_history_paths",
    "training_pipeline_summary_path",
    "training_pipeline_summary_paths",
    "write_feature_pipeline_run_summary",
    "write_training_pipeline_run_summary",
]
