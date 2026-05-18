"""Feature pipeline orchestration: fetch, engineer, validate, store."""

from __future__ import annotations

from datetime import UTC, datetime
import logging
from pathlib import Path
import re
import shutil
from time import perf_counter
from types import SimpleNamespace
from typing import Any

import mlflow
import pandas as pd

from foehncast._json import read_json_file_if_exists, write_pretty_json
from foehncast.config import (
    configure_mlflow_auth,
    get_mlflow_config,
    get_spots,
    get_storage_config,
)
from foehncast.feature_pipeline.engineer import engineer_features
from foehncast.feature_pipeline.ingest import fetch_all_spots
from foehncast.feature_pipeline.store import read_features, write_features
from foehncast.feature_pipeline.validate import run_validation, validation_snapshot
from foehncast.monitoring.drift import detect_data_drift, push_drift_metrics
from foehncast.monitoring.pipeline_metrics import (
    build_feature_pipeline_handoff_summary,
    build_feature_pipeline_run_summary,
    build_feature_pipeline_spot_summary,
    emit_feature_pipeline_run_summary,
)
from foehncast.orchestration._helpers import (
    resolve_auto_retraining_mode,
    scheduled_mlflow_tracking_uri,
)
from foehncast.paths import project_root
from foehncast.pipeline_stage_tracking import (
    FEATURE_PIPELINE_STAGES,
    increment_stage_failure,
    record_stage_duration,
)
from foehncast.pipeline_state import FeaturePipelineState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# State paths
# ---------------------------------------------------------------------------


def _feature_pipeline_state_root() -> Path:
    return project_root() / ".state" / "airflow" / "feature-pipeline"


def _sanitize_feature_pipeline_run_key(run_key: str | None = None) -> str:
    candidate = (run_key or datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%S%fZ")).strip()
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", candidate).strip(".-")
    return normalized or "manual"


def _feature_pipeline_run_dir(dataset: str, run_key: str | None = None) -> Path:
    return (
        _feature_pipeline_state_root()
        / dataset
        / _sanitize_feature_pipeline_run_key(run_key)
    )


def _feature_pipeline_stage_path(run_dir: Path, stage: str, spot_id: str) -> Path:
    return run_dir / stage / f"{spot_id}.pkl"


def _feature_pipeline_validation_path(run_dir: Path, spot_id: str) -> Path:
    return run_dir / "validation" / f"{spot_id}.json"


# ---------------------------------------------------------------------------
# Frame I/O helpers
# ---------------------------------------------------------------------------


def _write_feature_pipeline_frame(destination: Path, frame: pd.DataFrame) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    frame.to_pickle(destination)


def _read_feature_pipeline_frame(source: Path) -> pd.DataFrame:
    return pd.read_pickle(source)


def _read_optional_feature_pipeline_frame(source: Path) -> pd.DataFrame:
    if not source.exists():
        return pd.DataFrame()
    return _read_feature_pipeline_frame(source)


def _json_safe_feature_pipeline_value(value: Any) -> Any:
    if isinstance(value, (pd.Timestamp, datetime)):
        return None if pd.isna(value) else value.isoformat()

    if hasattr(value, "item") and callable(value.item):
        try:
            return _json_safe_feature_pipeline_value(value.item())
        except (TypeError, ValueError):
            pass

    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    return value


def _write_feature_pipeline_validation(
    destination: Path,
    validation: Any,
) -> None:
    snapshot = validation_snapshot(validation)
    range_violations = snapshot["range_violations"]
    payload = {
        "is_valid": snapshot["is_valid"],
        "missing_columns": snapshot["missing_columns"],
        "null_fractions": {
            str(column): _json_safe_feature_pipeline_value(null_fraction)
            for column, null_fraction in snapshot["null_fractions"].items()
        },
        "range_violations": (
            [
                {
                    str(key): _json_safe_feature_pipeline_value(value)
                    for key, value in record.items()
                }
                for record in range_violations.to_dict(orient="records")
            ]
            if isinstance(range_violations, pd.DataFrame)
            else []
        ),
    }
    write_pretty_json(destination, payload)


def _read_feature_pipeline_validation(source: Path) -> SimpleNamespace | None:
    payload = read_json_file_if_exists(source)
    if payload is None:
        return None

    return SimpleNamespace(
        is_valid=bool(payload.get("is_valid", False)),
        missing_columns=list(payload.get("missing_columns", [])),
        null_fractions=dict(payload.get("null_fractions", {})),
        range_violations=pd.DataFrame(payload.get("range_violations", [])),
    )


# ---------------------------------------------------------------------------
# Context helpers
# ---------------------------------------------------------------------------


def _copy_feature_pipeline_context(
    feature_context: FeaturePipelineState,
) -> FeaturePipelineState:
    return feature_context.copy()


def _feature_pipeline_context(
    dataset: str = "train",
    *,
    run_key: str | None = None,
) -> FeaturePipelineState:
    spots = get_spots()
    resolved_run_key = _sanitize_feature_pipeline_run_key(run_key)
    run_dir = _feature_pipeline_run_dir(dataset, resolved_run_key)

    return FeaturePipelineState.new(
        dataset=dataset,
        run_key=resolved_run_key,
        run_dir=run_dir,
        storage_backend=str(get_storage_config()["backend"]),
        expected_spots=[str(spot["id"]) for spot in spots],
        spot_config={
            str(spot["id"]): {
                "shore_orientation_deg": spot["shore_orientation_deg"],
            }
            for spot in spots
        },
    )


def _feature_pipeline_metric_count(
    feature_result: dict[str, object],
    *,
    count_key: str,
    items_key: str,
) -> int | None:
    if count_key in feature_result:
        return int(feature_result[count_key])
    if items_key in feature_result:
        return int(len(feature_result.get(items_key, [])))
    return None


# ---------------------------------------------------------------------------
# Result and summary
# ---------------------------------------------------------------------------


def _feature_pipeline_result(
    feature_context: FeaturePipelineState,
    *,
    auto_retraining_mode: str | None = None,
    training_request_stage: str = "Production",
) -> dict[str, object]:
    context = _copy_feature_pipeline_context(feature_context)
    expected_spots = list(context.expected_spots)
    fetched_spots = list(context.fetched_spots)
    engineered_spots = list(context.engineered_spots)
    validated_spots = list(context.validated_spots)
    stored_spots = list(context.stored_spots)
    drifted_spots = list(context.drifted_spots)
    stage_durations_seconds = dict(context.stage_durations_seconds)
    stage_failure_counts = {
        str(stage): int(count) for stage, count in context.stage_failure_counts.items()
    }
    handoff = build_feature_pipeline_handoff_summary(
        dataset=context.dataset,
        stored_spots=stored_spots,
        drifted_spots=drifted_spots,
        auto_retraining_mode=auto_retraining_mode,
        training_request_stage=training_request_stage,
    )

    return {
        "dataset": context.dataset,
        "storage_backend": context.storage_backend,
        "expected_spots": expected_spots,
        "fetched_spots": fetched_spots,
        "engineered_spots": engineered_spots,
        "validated_spots": validated_spots,
        "stored_spots": stored_spots,
        "drifted_spots": drifted_spots,
        "expected_spot_count": len(expected_spots),
        "fetched_spot_count": len(fetched_spots),
        "engineered_spot_count": len(engineered_spots),
        "validated_spot_count": len(validated_spots),
        "stored_spot_count": len(stored_spots),
        "stage_durations_seconds": stage_durations_seconds,
        "stage_failure_counts": stage_failure_counts,
        **handoff,
    }


def _emit_feature_pipeline_summary(
    feature_context: FeaturePipelineState,
    *,
    run_status: str,
    error: str | None = None,
    auto_retraining_mode: str | None = None,
    training_request_stage: str = "Production",
) -> None:
    context = _copy_feature_pipeline_context(feature_context)
    run_dir = context.run_dir
    fetched_spots = set(context.fetched_spots)
    stored_spots = set(context.stored_spots)
    spot_errors = dict(context.spot_errors)
    spot_summaries: list[dict[str, object]] = []

    has_stage_artifacts = run_dir.exists() and any(run_dir.rglob("*"))

    if (
        run_status == "failed"
        and not fetched_spots
        and not spot_errors
        and not has_stage_artifacts
    ):
        summary = build_feature_pipeline_run_summary(
            dataset=context.dataset,
            storage_backend=context.storage_backend,
            expected_spots=list(context.expected_spots),
            fetched_spots=[],
            engineered_spots=[],
            validated_spots=[],
            stored_spots=[],
            drifted_spots=[],
            stage_durations_seconds=dict(context.stage_durations_seconds),
            stage_failure_counts=dict(context.stage_failure_counts),
            spot_summaries=[],
            run_status=run_status,
            error=error,
            auto_retraining_mode=auto_retraining_mode,
            training_request_stage=training_request_stage,
        )
        emit_feature_pipeline_run_summary(summary)
        return

    for spot_id in context.expected_spots:
        forecast_df = _read_optional_feature_pipeline_frame(
            _feature_pipeline_stage_path(run_dir, "forecast", spot_id)
        )
        feature_df = _read_optional_feature_pipeline_frame(
            _feature_pipeline_stage_path(run_dir, "feature", spot_id)
        )
        validation = _read_feature_pipeline_validation(
            _feature_pipeline_validation_path(run_dir, spot_id)
        )
        stored_df = _read_optional_feature_pipeline_frame(
            _feature_pipeline_stage_path(run_dir, "stored", spot_id)
        )

        status = "stored"
        if spot_id not in stored_spots:
            status = "failed" if spot_id in spot_errors else "skipped"

        spot_summaries.append(
            build_feature_pipeline_spot_summary(
                spot_id=spot_id,
                forecast_df=forecast_df,
                feature_df=feature_df,
                validation=validation,
                stored_df=stored_df,
                status=status,
                error=spot_errors.get(spot_id),
            )
        )

    summary = build_feature_pipeline_run_summary(
        dataset=context.dataset,
        storage_backend=context.storage_backend,
        expected_spots=list(context.expected_spots),
        fetched_spots=list(context.fetched_spots),
        engineered_spots=list(context.engineered_spots),
        validated_spots=list(context.validated_spots),
        stored_spots=list(context.stored_spots),
        drifted_spots=list(context.drifted_spots),
        stage_durations_seconds=dict(context.stage_durations_seconds),
        stage_failure_counts=dict(context.stage_failure_counts),
        spot_summaries=spot_summaries,
        run_status=run_status,
        error=error,
        auto_retraining_mode=auto_retraining_mode,
        training_request_stage=training_request_stage,
    )
    emit_feature_pipeline_run_summary(summary)


# ---------------------------------------------------------------------------
# Drift helpers (used within the feature store step)
# ---------------------------------------------------------------------------


def _feature_drift_frame(
    frame: pd.DataFrame,
    *,
    spot_id: str,
    dataset: str,
) -> pd.DataFrame:
    tagged = frame.copy()
    tagged.attrs = {
        **getattr(tagged, "attrs", {}),
        "dataset_name": spot_id,
        "dataset_version": dataset,
    }
    return tagged


def _emit_feature_drift_metrics(
    *,
    spot_id: str,
    dataset: str,
    reference_df: pd.DataFrame,
    current_df: pd.DataFrame,
) -> bool:
    if reference_df.empty or current_df.empty:
        return False

    try:
        report = detect_data_drift(
            _feature_drift_frame(reference_df, spot_id=spot_id, dataset=dataset),
            _feature_drift_frame(current_df, spot_id=spot_id, dataset=dataset),
        )
        push_drift_metrics(report)
        return report.dataset_drift
    except Exception:
        logger.exception(
            "Failed to emit feature drift metrics for spot '%s' in dataset '%s'",
            spot_id,
            dataset,
        )
        return False


def _read_optional_feature_slice(spot_id: str, dataset: str) -> pd.DataFrame:
    try:
        return read_features(spot_id=spot_id, dataset=dataset)
    except Exception:
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# Pipeline stages (Airflow task callables)
# ---------------------------------------------------------------------------


def _fetch_feature_pipeline_context_state(
    dataset: str = "train",
    run_key: str | None = None,
) -> FeaturePipelineState:
    context = _feature_pipeline_context(dataset=dataset, run_key=run_key)
    run_dir = context.run_dir
    started_at = perf_counter()

    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    try:
        forecasts_by_spot = fetch_all_spots()
        fetched_spots: list[str] = []

        for spot_id in context.expected_spots:
            forecast_df = forecasts_by_spot.get(spot_id, pd.DataFrame())
            if forecast_df.empty:
                continue

            _write_feature_pipeline_frame(
                _feature_pipeline_stage_path(run_dir, "forecast", spot_id),
                forecast_df,
            )
            fetched_spots.append(spot_id)

        context.fetched_spots = fetched_spots
        record_stage_duration(
            context,
            stage="fetch",
            started_at=started_at,
        )
        _emit_feature_pipeline_summary(context, run_status="running")
        return context
    except Exception as exc:
        increment_stage_failure(
            context,
            stage="fetch",
            stage_names=FEATURE_PIPELINE_STAGES,
        )
        record_stage_duration(
            context,
            stage="fetch",
            started_at=started_at,
        )
        _emit_feature_pipeline_summary(context, run_status="failed", error=str(exc))
        raise


def fetch_feature_pipeline_context(
    dataset: str = "train",
    run_key: str | None = None,
) -> dict[str, object]:
    """Fetch forecasts and persist them for downstream Airflow feature tasks."""
    return _fetch_feature_pipeline_context_state(
        dataset=dataset,
        run_key=run_key,
    ).to_payload()


def _engineer_feature_pipeline_context_state(
    feature_context: FeaturePipelineState,
) -> FeaturePipelineState:
    context = _copy_feature_pipeline_context(feature_context)
    run_dir = context.run_dir
    engineered_spots: list[str] = []
    started_at = perf_counter()

    try:
        for spot_id in context.fetched_spots:
            try:
                forecast_df = _read_feature_pipeline_frame(
                    _feature_pipeline_stage_path(run_dir, "forecast", spot_id)
                )
                feature_df = engineer_features(
                    forecast_df,
                    context.spot_config[spot_id]["shore_orientation_deg"],
                )
                _write_feature_pipeline_frame(
                    _feature_pipeline_stage_path(run_dir, "feature", spot_id),
                    feature_df,
                )
                engineered_spots.append(spot_id)
            except Exception as exc:
                context.engineered_spots = engineered_spots
                context.spot_errors[spot_id] = str(exc)
                increment_stage_failure(
                    context,
                    stage="engineer",
                    stage_names=FEATURE_PIPELINE_STAGES,
                )
                record_stage_duration(
                    context,
                    stage="engineer",
                    started_at=started_at,
                )
                _emit_feature_pipeline_summary(
                    context,
                    run_status="failed",
                    error=str(exc),
                )
                raise

            context.engineered_spots = engineered_spots
        record_stage_duration(
            context,
            stage="engineer",
            started_at=started_at,
        )
        _emit_feature_pipeline_summary(context, run_status="running")
        return context
    except Exception:
        raise


def engineer_feature_pipeline_context(
    feature_context: dict[str, object],
) -> dict[str, object]:
    """Engineer features from fetched forecasts for downstream Airflow tasks."""
    return _engineer_feature_pipeline_context_state(
        FeaturePipelineState.from_payload(feature_context)
    ).to_payload()


def _validate_feature_pipeline_context_state(
    feature_context: FeaturePipelineState,
) -> FeaturePipelineState:
    context = _copy_feature_pipeline_context(feature_context)
    run_dir = context.run_dir
    validated_spots: list[str] = []
    started_at = perf_counter()

    try:
        for spot_id in context.engineered_spots:
            try:
                feature_df = _read_feature_pipeline_frame(
                    _feature_pipeline_stage_path(run_dir, "feature", spot_id)
                )
                validation = run_validation(feature_df, spot_id)
                _write_feature_pipeline_validation(
                    _feature_pipeline_validation_path(run_dir, spot_id),
                    validation,
                )
                if not validation.is_valid:
                    raise ValueError(f"Feature validation failed for spot '{spot_id}'")
                validated_spots.append(spot_id)
            except Exception as exc:
                context.validated_spots = validated_spots
                context.spot_errors[spot_id] = str(exc)
                increment_stage_failure(
                    context,
                    stage="validate",
                    stage_names=FEATURE_PIPELINE_STAGES,
                )
                record_stage_duration(
                    context,
                    stage="validate",
                    started_at=started_at,
                )
                _emit_feature_pipeline_summary(
                    context,
                    run_status="failed",
                    error=str(exc),
                )
                raise

            context.validated_spots = validated_spots
        record_stage_duration(
            context,
            stage="validate",
            started_at=started_at,
        )
        _emit_feature_pipeline_summary(context, run_status="running")
        return context
    except Exception:
        raise


def validate_feature_pipeline_context(
    feature_context: dict[str, object],
) -> dict[str, object]:
    """Validate engineered features and persist validation outcomes."""
    return _validate_feature_pipeline_context_state(
        FeaturePipelineState.from_payload(feature_context)
    ).to_payload()


def _store_feature_pipeline_context_state(
    feature_context: FeaturePipelineState,
    *,
    auto_retraining_mode: str | None = None,
    training_request_stage: str = "Production",
) -> dict[str, object]:
    context = _copy_feature_pipeline_context(feature_context)
    run_dir = context.run_dir
    stored_spots: list[str] = []
    drifted_spots: list[str] = []
    started_at = perf_counter()

    try:
        for spot_id in context.validated_spots:
            try:
                feature_df = _read_feature_pipeline_frame(
                    _feature_pipeline_stage_path(run_dir, "feature", spot_id)
                )
                previous_stored_df = _read_optional_feature_slice(
                    spot_id,
                    context.dataset,
                )
                write_features(
                    feature_df,
                    spot_id=spot_id,
                    dataset=context.dataset,
                )
                stored_df = read_features(
                    spot_id=spot_id,
                    dataset=context.dataset,
                )
                _write_feature_pipeline_frame(
                    _feature_pipeline_stage_path(run_dir, "stored", spot_id),
                    stored_df,
                )

                if _emit_feature_drift_metrics(
                    spot_id=spot_id,
                    dataset=context.dataset,
                    reference_df=previous_stored_df,
                    current_df=stored_df,
                ):
                    drifted_spots.append(spot_id)

                stored_spots.append(spot_id)
            except Exception as exc:
                context.stored_spots = stored_spots
                context.drifted_spots = drifted_spots
                context.spot_errors[spot_id] = str(exc)
                increment_stage_failure(
                    context,
                    stage="store",
                    stage_names=FEATURE_PIPELINE_STAGES,
                )
                record_stage_duration(
                    context,
                    stage="store",
                    started_at=started_at,
                )
                _emit_feature_pipeline_summary(
                    context,
                    run_status="failed",
                    error=str(exc),
                    auto_retraining_mode=auto_retraining_mode,
                    training_request_stage=training_request_stage,
                )
                raise

        if not stored_spots:
            context.stored_spots = []
            context.drifted_spots = []
            error = "No feature data was generated for any configured spot"
            increment_stage_failure(
                context,
                stage="store",
                stage_names=FEATURE_PIPELINE_STAGES,
            )
            record_stage_duration(
                context,
                stage="store",
                started_at=started_at,
            )
            _emit_feature_pipeline_summary(
                context,
                run_status="failed",
                error=error,
                auto_retraining_mode=auto_retraining_mode,
                training_request_stage=training_request_stage,
            )
            raise ValueError(error)

        context.stored_spots = stored_spots
        context.drifted_spots = drifted_spots
        record_stage_duration(
            context,
            stage="store",
            started_at=started_at,
        )
        _emit_feature_pipeline_summary(
            context,
            run_status="succeeded",
            auto_retraining_mode=auto_retraining_mode,
            training_request_stage=training_request_stage,
        )
        return _feature_pipeline_result(
            context,
            auto_retraining_mode=auto_retraining_mode,
            training_request_stage=training_request_stage,
        )
    except Exception:
        raise


def store_feature_pipeline_context(
    feature_context: dict[str, object],
    auto_retraining_mode: str | None = None,
    training_request_stage: str = "Production",
) -> dict[str, object]:
    """Store validated features, emit drift metrics, and return retraining context."""
    resolved_mode = resolve_auto_retraining_mode(auto_retraining_mode, default=None)
    return _store_feature_pipeline_context_state(
        FeaturePipelineState.from_payload(feature_context),
        auto_retraining_mode=resolved_mode,
        training_request_stage=training_request_stage,
    )


def _log_feature_pipeline_job_context(feature_result: dict[str, object]) -> None:
    tracking_uri = scheduled_mlflow_tracking_uri()
    if tracking_uri is None:
        return

    mlflow.set_tracking_uri(tracking_uri)
    configure_mlflow_auth()
    mlflow.set_experiment(get_mlflow_config()["experiment_name"])

    metrics: dict[str, float] = {}
    for count_key, items_key in (
        ("expected_spot_count", "expected_spots"),
        ("fetched_spot_count", "fetched_spots"),
        ("engineered_spot_count", "engineered_spots"),
        ("validated_spot_count", "validated_spots"),
        ("stored_spot_count", "stored_spots"),
        ("drifted_spot_count", "drifted_spots"),
    ):
        count = _feature_pipeline_metric_count(
            feature_result,
            count_key=count_key,
            items_key=items_key,
        )
        if count is not None:
            metrics[count_key] = float(count)

    for stage, duration in dict(
        feature_result.get("stage_durations_seconds", {})
    ).items():
        metrics[f"{stage}_duration_seconds"] = float(duration)

    for stage, count in dict(feature_result.get("stage_failure_counts", {})).items():
        metrics[f"{stage}_failure_count"] = float(count)

    metrics["dataset_drift_detected"] = float(
        feature_result.get("dataset_drift_detected", False)
    )
    metrics["feature_persistence_ready"] = float(
        feature_result.get("feature_persistence_ready", False)
    )
    metrics["training_handoff_ready"] = float(
        feature_result.get("training_handoff_ready", False)
    )

    with mlflow.start_run(run_name=f"feature-{feature_result['dataset']}-refresh"):
        params = {
            "dataset": feature_result["dataset"],
            "storage_backend": feature_result["storage_backend"],
            "stored_spots": ",".join(feature_result.get("stored_spots", [])),
            "drifted_spots": ",".join(feature_result.get("drifted_spots", [])),
        }
        if feature_result.get("training_handoff_mode"):
            params["training_handoff_mode"] = str(
                feature_result["training_handoff_mode"]
            )
        if feature_result.get("training_request_stage"):
            params["training_request_stage"] = str(
                feature_result["training_request_stage"]
            )
        mlflow.log_params(params)
        for name, value in metrics.items():
            mlflow.log_metric(name, value)


def store_feature_pipeline_job_context(
    feature_context: dict[str, object],
    auto_retraining_mode: str | None = None,
    training_request_stage: str = "Production",
) -> dict[str, object]:
    """Store validated features and log the final Airflow-friendly refresh context."""
    result = store_feature_pipeline_context(
        feature_context,
        auto_retraining_mode=auto_retraining_mode,
        training_request_stage=training_request_stage,
    )
    _log_feature_pipeline_job_context(result)
    return result


# ---------------------------------------------------------------------------
# Convenience runners (all-in-one)
# ---------------------------------------------------------------------------


def _run_feature_pipeline_result(
    dataset: str = "train",
    *,
    auto_retraining_mode: str | None = None,
    training_request_stage: str = "Production",
) -> dict[str, object]:
    """Run the feature pipeline and return stored spots plus retraining context."""
    feature_context = _fetch_feature_pipeline_context_state(dataset=dataset)
    feature_context = _engineer_feature_pipeline_context_state(feature_context)
    feature_context = _validate_feature_pipeline_context_state(feature_context)
    return _store_feature_pipeline_context_state(
        feature_context,
        auto_retraining_mode=resolve_auto_retraining_mode(
            auto_retraining_mode,
            default=None,
        ),
        training_request_stage=training_request_stage,
    )


def run_feature_pipeline(dataset: str = "train") -> list[str]:
    """Fetch, engineer, validate, store, and monitor features for all spots."""
    return list(_run_feature_pipeline_result(dataset=dataset)["stored_spots"])


def run_feature_pipeline_job(dataset: str = "train") -> list[str]:
    """Run the feature pipeline and optionally log a refresh run to MLflow."""
    tracking_uri = scheduled_mlflow_tracking_uri()
    if tracking_uri is None:
        return run_feature_pipeline(dataset=dataset)

    mlflow.set_tracking_uri(tracking_uri)
    configure_mlflow_auth()
    mlflow.set_experiment(get_mlflow_config()["experiment_name"])

    with mlflow.start_run(run_name=f"feature-{dataset}-refresh"):
        stored_spots = run_feature_pipeline(dataset=dataset)
        mlflow.log_params(
            {
                "dataset": dataset,
                "storage_backend": get_storage_config()["backend"],
                "stored_spots": ",".join(stored_spots),
            }
        )
        mlflow.log_metric("stored_spot_count", len(stored_spots))
        return stored_spots


def run_feature_pipeline_job_context(
    dataset: str = "train",
    *,
    auto_retraining_mode: str | None = None,
    training_request_stage: str = "Production",
) -> dict[str, object]:
    """Run the feature pipeline and return Airflow-friendly retraining context."""
    result = _run_feature_pipeline_result(
        dataset=dataset,
        auto_retraining_mode=auto_retraining_mode,
        training_request_stage=training_request_stage,
    )
    _log_feature_pipeline_job_context(result)
    return result
