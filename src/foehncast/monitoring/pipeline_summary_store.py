"""Compatibility wrappers for pipeline summary persistence helpers."""

from __future__ import annotations

from foehncast.monitoring.pipeline_metrics import (
    feature_pipeline_summary_history_paths,
    feature_pipeline_summary_path,
    feature_pipeline_summary_paths,
    read_all_feature_pipeline_run_summaries,
    read_all_training_pipeline_run_summaries,
    read_feature_pipeline_run_summary,
    read_feature_pipeline_run_summary_history,
    read_training_pipeline_run_summary,
    read_training_pipeline_run_summary_history,
    training_pipeline_summary_history_paths,
    training_pipeline_summary_path,
    training_pipeline_summary_paths,
    write_feature_pipeline_run_summary,
    write_training_pipeline_run_summary,
)

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
