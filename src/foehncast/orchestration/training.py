"""Training pipeline orchestration: train, evaluate, register."""

from __future__ import annotations

from collections.abc import Callable
import logging
from pathlib import Path
from time import perf_counter
from typing import Any

import mlflow

from foehncast.config import (
    configure_mlflow_auth,
    get_mlflow_config,
    get_mlflow_tracking_uri,
)
from foehncast.monitoring.pipeline_metrics import (
    build_training_pipeline_run_summary,
    emit_training_pipeline_run_summary,
    read_training_pipeline_run_summary,
    read_training_pipeline_run_summary_history,
)
from foehncast.paths import project_root
from foehncast.pipeline_stage_tracking import (
    TRAINING_PIPELINE_STAGES,
    increment_stage_failure,
    record_stage_duration,
)
from foehncast.pipeline_state import TrainingPipelineState
from foehncast.training_pipeline.evaluate import generate_evaluation_report
from foehncast.training_pipeline.register import promote_model, register_model
from foehncast.training_pipeline.train import run_training_pipeline

logger = logging.getLogger(__name__)


# Summary state management


def _training_summary_state(
    *,
    dataset: str,
    requested_stage: str,
    training_run_id: str | None = None,
) -> TrainingPipelineState:
    summary: dict[str, Any] = {}

    try:
        latest_summary = read_training_pipeline_run_summary(dataset)
    except FileNotFoundError:
        latest_summary = {}

    if not training_run_id or latest_summary.get("training_run_id") in {
        None,
        training_run_id,
    }:
        summary = latest_summary
    else:
        try:
            summary_history = read_training_pipeline_run_summary_history(dataset)
        except FileNotFoundError:
            summary_history = []

        for candidate in reversed(summary_history):
            if candidate.get("training_run_id") == training_run_id:
                summary = candidate
                break

    return TrainingPipelineState.from_summary(
        dataset=dataset,
        requested_stage=requested_stage,
        summary=summary,
        training_run_id=training_run_id,
    )


def _emit_training_summary(
    training_state: TrainingPipelineState,
    *,
    run_status: str,
    error: str | None = None,
) -> None:
    summary = build_training_pipeline_run_summary(
        **training_state.to_summary_payload(),
        run_status=run_status,
        error=error,
    )
    emit_training_pipeline_run_summary(summary)


def _run_training_stage(
    training_state: TrainingPipelineState,
    *,
    stage: str,
    success_status: str,
    action: Callable[[], Any],
) -> Any:
    started_at = perf_counter()

    try:
        result = action()
    except Exception as exc:
        increment_stage_failure(
            training_state,
            stage=stage,
            stage_names=TRAINING_PIPELINE_STAGES,
        )
        record_stage_duration(
            training_state,
            stage=stage,
            started_at=started_at,
        )
        _emit_training_summary(training_state, run_status="failed", error=str(exc))
        raise

    record_stage_duration(
        training_state,
        stage=stage,
        started_at=started_at,
    )
    _emit_training_summary(training_state, run_status=success_status)
    return result


# MLflow run introspection


def _training_run_metrics_and_params(
    training_run_id: str,
) -> tuple[dict[str, float], dict[str, str]]:
    run = mlflow.MlflowClient().get_run(training_run_id)
    raw_metrics = dict(getattr(run.data, "metrics", {}))
    raw_params = dict(getattr(run.data, "params", {}))
    metrics = {str(name): float(value) for name, value in raw_metrics.items()}
    params = {str(name): str(value) for name, value in raw_params.items()}
    return metrics, params


def _training_run_snapshot(training_run_id: str) -> dict[str, Any]:
    metrics, params = _training_run_metrics_and_params(training_run_id)

    def _metric_count(name: str) -> int | None:
        value = metrics.get(name)
        return None if value is None else int(value)

    return {
        "run_metrics": metrics,
        "training_row_count": _metric_count("training_input_row_count"),
        "training_feature_count": _metric_count("training_feature_count"),
        "train_row_count": _metric_count("training_train_row_count"),
        "test_row_count": _metric_count("training_test_row_count"),
        "registered_model_name": params.get("model_name"),
    }


# Pipeline steps (Airflow task callables)


def run_training_pipeline_step(
    dataset: str = "train",
    requested_stage: str = "Candidate",
) -> str:
    """Train the model and persist the latest step-level training summary."""
    training_state = TrainingPipelineState.from_summary(
        dataset=dataset,
        requested_stage=requested_stage,
        summary={},
    )

    def _run() -> str:
        training_run_id = run_training_pipeline(dataset=dataset)
        training_state.merge_run_snapshot(_training_run_snapshot(training_run_id))
        training_state.training_run_id = training_run_id
        return training_run_id

    return _run_training_stage(
        training_state,
        stage="train",
        success_status="running",
        action=_run,
    )


def evaluate_training_run(
    training_run_id: str,
    dataset: str = "train",
    requested_stage: str = "Candidate",
) -> str:
    """Resume a training run, log evaluation metrics, and return the report path."""
    training_state = _training_summary_state(
        dataset=dataset,
        requested_stage=requested_stage,
        training_run_id=training_run_id,
    )

    def _run() -> str:
        mlflow.set_tracking_uri(get_mlflow_tracking_uri())
        configure_mlflow_auth()
        metrics, _ = _training_run_metrics_and_params(training_run_id)
        if not metrics:
            raise ValueError(f"No evaluation metrics found for run '{training_run_id}'")

        report_dir = project_root() / "airflow" / "reports"
        report_path = report_dir / f"evaluation-{training_run_id}.md"

        with mlflow.start_run(run_id=training_run_id):
            resolved_report_path = generate_evaluation_report(metrics, str(report_path))

        training_state.training_run_id = training_run_id
        training_state.run_metrics = metrics
        training_state.evaluation_report_path = resolved_report_path
        training_state.evaluation_report_exists = Path(resolved_report_path).exists()
        return resolved_report_path

    return _run_training_stage(
        training_state,
        stage="evaluate",
        success_status="running",
        action=_run,
    )


def register_training_run(
    training_run_id: str,
    stage: str = "Candidate",
    dataset: str = "train",
) -> str:
    """Register a training run's model and assign the requested registry alias."""
    training_state = _training_summary_state(
        dataset=dataset,
        requested_stage=stage,
        training_run_id=training_run_id,
    )

    def _run() -> str:
        model_version = register_model(training_run_id)
        promote_model(None, model_version.version, stage=stage)
        training_state.training_run_id = training_run_id
        training_state.registered_model_name = get_mlflow_config()["model_name"]
        training_state.registered_model_version = str(model_version.version)
        return str(model_version.version)

    return _run_training_stage(
        training_state,
        stage="register",
        success_status="succeeded",
        action=_run,
    )
