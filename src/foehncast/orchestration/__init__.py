"""High-level orchestration helpers for Airflow-managed ML jobs.

This package re-exports the public API from domain-specific submodules
for backward compatibility with existing DAGs and tests.
"""

from foehncast.orchestration._helpers import (
    resolve_airflow_schedule,
    resolve_auto_retraining_mode,
    should_auto_retrain,
)
from foehncast.orchestration.drift import (
    run_feature_drift_detection_step,
    run_prediction_drift_detection_step,
)
from foehncast.orchestration.feature import (
    _copy_feature_pipeline_context,
    _emit_feature_drift_metrics,
    _emit_feature_pipeline_summary,
    _engineer_feature_pipeline_context_state,
    _feature_pipeline_context,
    _feature_pipeline_metric_count,
    _feature_pipeline_result,
    _feature_pipeline_run_dir,
    _feature_pipeline_stage_path,
    _feature_pipeline_state_root,
    _feature_pipeline_validation_path,
    _fetch_feature_pipeline_context_state,
    _json_safe_feature_pipeline_value,
    _log_feature_pipeline_job_context,
    _read_feature_pipeline_frame,
    _read_feature_pipeline_validation,
    _read_optional_feature_pipeline_frame,
    _read_optional_feature_slice,
    _run_feature_pipeline_result,
    _sanitize_feature_pipeline_run_key,
    _store_feature_pipeline_context_state,
    _validate_feature_pipeline_context_state,
    _write_feature_pipeline_frame,
    _write_feature_pipeline_validation,
    engineer_feature_pipeline_context,
    fetch_feature_pipeline_context,
    run_feature_pipeline,
    run_feature_pipeline_job,
    run_feature_pipeline_job_context,
    store_feature_pipeline_context,
    store_feature_pipeline_job_context,
    validate_feature_pipeline_context,
)
from foehncast.orchestration.inference import run_inference_pipeline_step
from foehncast.orchestration.training import (
    _training_run_metrics_and_params,
    _training_run_snapshot,
    _training_summary_state,
    evaluate_training_run,
    register_training_run,
    run_training_pipeline_step,
)

__all__ = [
    # Helpers
    "resolve_airflow_schedule",
    "resolve_auto_retraining_mode",
    "should_auto_retrain",
    # Feature pipeline
    "_copy_feature_pipeline_context",
    "_emit_feature_drift_metrics",
    "_emit_feature_pipeline_summary",
    "_engineer_feature_pipeline_context_state",
    "_feature_pipeline_context",
    "_feature_pipeline_metric_count",
    "_feature_pipeline_result",
    "_feature_pipeline_run_dir",
    "_feature_pipeline_stage_path",
    "_feature_pipeline_state_root",
    "_feature_pipeline_validation_path",
    "_fetch_feature_pipeline_context_state",
    "_json_safe_feature_pipeline_value",
    "_log_feature_pipeline_job_context",
    "_read_feature_pipeline_frame",
    "_read_feature_pipeline_validation",
    "_read_optional_feature_pipeline_frame",
    "_read_optional_feature_slice",
    "_run_feature_pipeline_result",
    "_sanitize_feature_pipeline_run_key",
    "_store_feature_pipeline_context_state",
    "_validate_feature_pipeline_context_state",
    "_write_feature_pipeline_frame",
    "_write_feature_pipeline_validation",
    "engineer_feature_pipeline_context",
    "fetch_feature_pipeline_context",
    "run_feature_pipeline",
    "run_feature_pipeline_job",
    "run_feature_pipeline_job_context",
    "store_feature_pipeline_context",
    "store_feature_pipeline_job_context",
    "validate_feature_pipeline_context",
    # Training pipeline
    "_training_run_metrics_and_params",
    "_training_run_snapshot",
    "_training_summary_state",
    "evaluate_training_run",
    "register_training_run",
    "run_training_pipeline_step",
    # Inference pipeline
    "run_inference_pipeline_step",
    # Drift
    "run_feature_drift_detection_step",
    "run_prediction_drift_detection_step",
]
