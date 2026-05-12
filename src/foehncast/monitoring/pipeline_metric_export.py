"""MLflow export helpers for pipeline monitoring summaries."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

SummaryWriter = Callable[[dict[str, Any]], Path]


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
    if version is not None and str(version).strip().isdigit():
        metrics["training_registered_model_version"] = float(version)

    for stage, duration in dict(summary.get("stage_durations_seconds", {})).items():
        metrics[f"training_{stage}_duration_seconds"] = float(duration)

    for stage, count in dict(summary.get("stage_failure_counts", {})).items():
        metrics[f"training_{stage}_failure_count"] = float(count)

    for name, value in dict(summary.get("run_metrics", {})).items():
        metrics[f"training_metric_{name}"] = float(value)

    return metrics


def emit_feature_pipeline_run_summary(
    summary: dict[str, Any],
    *,
    writer: SummaryWriter,
    mlflow_module: Any,
) -> Path:
    """Persist the latest summary and mirror stable metrics into MLflow if active."""
    summary_path = writer(summary)
    active_run = getattr(mlflow_module, "active_run", lambda: None)()
    if active_run is None:
        return summary_path

    mlflow_module.log_metrics(feature_pipeline_summary_metrics(summary))
    mlflow_module.log_artifact(
        str(summary_path),
        artifact_path="monitoring/feature_pipeline",
    )
    return summary_path


def emit_training_pipeline_run_summary(
    summary: dict[str, Any],
    *,
    writer: SummaryWriter,
    mlflow_module: Any,
) -> Path:
    """Persist the latest summary and mirror stable training metrics into MLflow if active."""
    summary_path = writer(summary)
    active_run = getattr(mlflow_module, "active_run", lambda: None)()
    if active_run is None:
        return summary_path

    mlflow_module.log_metrics(training_pipeline_summary_metrics(summary))
    mlflow_module.log_artifact(
        str(summary_path),
        artifact_path="monitoring/training_pipeline",
    )
    return summary_path


__all__ = [
    "emit_feature_pipeline_run_summary",
    "emit_training_pipeline_run_summary",
    "feature_pipeline_summary_metrics",
    "training_pipeline_summary_metrics",
]
