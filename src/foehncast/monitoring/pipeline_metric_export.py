"""Compatibility wrappers for pipeline MLflow export helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from foehncast.monitoring import pipeline_metrics

SummaryWriter = Callable[[dict[str, Any]], Path]

feature_pipeline_summary_metrics = pipeline_metrics.feature_pipeline_summary_metrics
training_pipeline_summary_metrics = pipeline_metrics.training_pipeline_summary_metrics


def emit_feature_pipeline_run_summary(
    summary: dict[str, Any],
    *,
    writer: SummaryWriter,
    mlflow_module: Any,
) -> Path:
    return pipeline_metrics._emit_summary(
        summary,
        writer=writer,
        metrics_builder=feature_pipeline_summary_metrics,
        artifact_path="monitoring/feature_pipeline",
        mlflow_module=mlflow_module,
    )


def emit_training_pipeline_run_summary(
    summary: dict[str, Any],
    *,
    writer: SummaryWriter,
    mlflow_module: Any,
) -> Path:
    return pipeline_metrics._emit_summary(
        summary,
        writer=writer,
        metrics_builder=training_pipeline_summary_metrics,
        artifact_path="monitoring/training_pipeline",
        mlflow_module=mlflow_module,
    )


__all__ = [
    "emit_feature_pipeline_run_summary",
    "emit_training_pipeline_run_summary",
    "feature_pipeline_summary_metrics",
    "training_pipeline_summary_metrics",
]
