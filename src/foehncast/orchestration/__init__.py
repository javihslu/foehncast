"""High-level orchestration helpers for Airflow-managed ML jobs.

This package re-exports the public API from domain-specific submodules.
"""

from foehncast.orchestration._helpers import (
    resolve_airflow_schedule,
    resolve_auto_retraining_mode,
    should_auto_retrain,
)
from foehncast.orchestration.drift import (
    run_feature_drift_detection_step,
    run_forecast_feature_drift_detection_step,
    run_prediction_drift_detection_step,
)
from foehncast.orchestration.feature import (
    engineer_feature_pipeline_context,
    fetch_feature_pipeline_context,
    prepare_feast_feature_store,
    run_feature_pipeline,
    run_feature_pipeline_job,
    run_feature_pipeline_job_context,
    store_feature_pipeline_context,
    store_feature_pipeline_job_context,
    validate_feature_pipeline_context,
)
from foehncast.orchestration.inference import run_inference_pipeline_step
from foehncast.orchestration.training import (
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
    "engineer_feature_pipeline_context",
    "fetch_feature_pipeline_context",
    "prepare_feast_feature_store",
    "run_feature_pipeline",
    "run_feature_pipeline_job",
    "run_feature_pipeline_job_context",
    "store_feature_pipeline_context",
    "store_feature_pipeline_job_context",
    "validate_feature_pipeline_context",
    # Training pipeline
    "evaluate_training_run",
    "register_training_run",
    "run_training_pipeline_step",
    # Inference pipeline
    "run_inference_pipeline_step",
    # Drift
    "run_feature_drift_detection_step",
    "run_forecast_feature_drift_detection_step",
    "run_prediction_drift_detection_step",
]
