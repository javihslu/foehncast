"""High-level orchestration helpers for Airflow-managed ML jobs."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import logging
import os
from pathlib import Path
import re
import shutil
from time import perf_counter
from types import SimpleNamespace
from typing import Any

import mlflow
import pandas as pd

from foehncast.config import (
    get_mlflow_config,
    get_mlflow_tracking_uri,
    get_spots,
    get_storage_config,
)
from foehncast.feature_pipeline.engineer import engineer_features
from foehncast.feature_pipeline.ingest import fetch_all_spots
from foehncast.feature_pipeline.store import read_features, write_features
from foehncast.feature_pipeline.validate import run_validation
from foehncast.monitoring.drift import detect_data_drift, push_drift_metrics
from foehncast.monitoring.pipeline_metrics import (
    FEATURE_PIPELINE_STAGES,
    TRAINING_PIPELINE_STAGES,
    build_feature_pipeline_run_summary,
    build_feature_pipeline_spot_summary,
    build_training_pipeline_run_summary,
    emit_feature_pipeline_run_summary,
    emit_training_pipeline_run_summary,
    read_training_pipeline_run_summary,
)
from foehncast.paths import project_root
from foehncast.training_pipeline.evaluate import generate_evaluation_report
from foehncast.training_pipeline.register import promote_model, register_model
from foehncast.training_pipeline.train import run_training_pipeline

logger = logging.getLogger(__name__)


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
    destination.parent.mkdir(parents=True, exist_ok=True)
    range_violations = getattr(validation, "range_violations", None)
    payload = {
        "is_valid": bool(getattr(validation, "is_valid", False)),
        "missing_columns": list(getattr(validation, "missing_columns", []) or []),
        "null_fractions": {
            str(column): _json_safe_feature_pipeline_value(null_fraction)
            for column, null_fraction in dict(
                getattr(validation, "null_fractions", {}) or {}
            ).items()
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
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _read_feature_pipeline_validation(source: Path) -> SimpleNamespace | None:
    if not source.exists():
        return None

    payload = json.loads(source.read_text())
    return SimpleNamespace(
        is_valid=bool(payload.get("is_valid", False)),
        missing_columns=list(payload.get("missing_columns", [])),
        null_fractions=dict(payload.get("null_fractions", {})),
        range_violations=pd.DataFrame(payload.get("range_violations", [])),
    )


def _copy_feature_pipeline_context(
    feature_context: dict[str, object],
) -> dict[str, object]:
    context = dict(feature_context)

    for key in (
        "expected_spots",
        "fetched_spots",
        "engineered_spots",
        "validated_spots",
        "stored_spots",
        "drifted_spots",
    ):
        context[key] = list(feature_context.get(key, []))

    context["stage_durations_seconds"] = dict(
        feature_context.get("stage_durations_seconds", {})
    )
    context["stage_failure_counts"] = dict(
        feature_context.get("stage_failure_counts", {})
    )
    context["spot_config"] = dict(feature_context.get("spot_config", {}))
    context["spot_errors"] = dict(feature_context.get("spot_errors", {}))
    return context


def _set_feature_pipeline_stage_duration(
    feature_context: dict[str, object],
    *,
    stage: str,
    started_at: float,
) -> None:
    durations = dict(feature_context.get("stage_durations_seconds", {}))
    durations[str(stage)] = float(perf_counter() - started_at)
    feature_context["stage_durations_seconds"] = durations


def _increment_feature_pipeline_stage_failure(
    feature_context: dict[str, object],
    *,
    stage: str,
) -> None:
    counts = {
        known_stage: int(
            dict(feature_context.get("stage_failure_counts", {})).get(known_stage, 0)
        )
        for known_stage in FEATURE_PIPELINE_STAGES
    }
    counts[str(stage)] = int(counts.get(str(stage), 0)) + 1
    feature_context["stage_failure_counts"] = counts


def _feature_pipeline_context(
    dataset: str = "train",
    *,
    run_key: str | None = None,
) -> dict[str, object]:
    spots = get_spots()
    resolved_run_key = _sanitize_feature_pipeline_run_key(run_key)
    run_dir = _feature_pipeline_run_dir(dataset, resolved_run_key)

    return {
        "dataset": dataset,
        "run_key": resolved_run_key,
        "run_dir": str(run_dir),
        "storage_backend": get_storage_config()["backend"],
        "expected_spots": [str(spot["id"]) for spot in spots],
        "fetched_spots": [],
        "engineered_spots": [],
        "validated_spots": [],
        "stored_spots": [],
        "drifted_spots": [],
        "stage_durations_seconds": {},
        "stage_failure_counts": {stage: 0 for stage in FEATURE_PIPELINE_STAGES},
        "spot_errors": {},
        "spot_config": {
            str(spot["id"]): {
                "shore_orientation_deg": spot["shore_orientation_deg"],
            }
            for spot in spots
        },
    }


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


def _feature_pipeline_result(
    feature_context: dict[str, object],
) -> dict[str, object]:
    context = _copy_feature_pipeline_context(feature_context)
    expected_spots = list(context.get("expected_spots", []))
    fetched_spots = list(context.get("fetched_spots", []))
    engineered_spots = list(context.get("engineered_spots", []))
    validated_spots = list(context.get("validated_spots", []))
    stored_spots = list(context.get("stored_spots", []))
    drifted_spots = list(context.get("drifted_spots", []))
    stage_durations_seconds = dict(context.get("stage_durations_seconds", {}))
    stage_failure_counts = {
        str(stage): int(count)
        for stage, count in dict(context.get("stage_failure_counts", {})).items()
    }

    return {
        "dataset": context["dataset"],
        "storage_backend": context["storage_backend"],
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
        "drifted_spot_count": len(drifted_spots),
        "stage_durations_seconds": stage_durations_seconds,
        "stage_failure_counts": stage_failure_counts,
        "dataset_drift_detected": bool(drifted_spots),
    }


def _emit_feature_pipeline_summary(
    feature_context: dict[str, object],
    *,
    run_status: str,
    error: str | None = None,
) -> None:
    context = _copy_feature_pipeline_context(feature_context)
    run_dir = Path(str(context["run_dir"]))
    fetched_spots = set(context.get("fetched_spots", []))
    stored_spots = set(context.get("stored_spots", []))
    spot_errors = dict(context.get("spot_errors", {}))
    spot_summaries: list[dict[str, object]] = []

    has_stage_artifacts = run_dir.exists() and any(run_dir.rglob("*"))

    if (
        run_status == "failed"
        and not fetched_spots
        and not spot_errors
        and not has_stage_artifacts
    ):
        summary = build_feature_pipeline_run_summary(
            dataset=str(context["dataset"]),
            storage_backend=str(context["storage_backend"]),
            expected_spots=list(context.get("expected_spots", [])),
            fetched_spots=[],
            engineered_spots=[],
            validated_spots=[],
            stored_spots=[],
            stage_durations_seconds=dict(context.get("stage_durations_seconds", {})),
            stage_failure_counts=dict(context.get("stage_failure_counts", {})),
            spot_summaries=[],
            run_status=run_status,
            error=error,
        )
        emit_feature_pipeline_run_summary(summary)
        return

    for spot_id in context.get("expected_spots", []):
        forecast_df = _read_optional_feature_pipeline_frame(
            _feature_pipeline_stage_path(run_dir, "forecast", str(spot_id))
        )
        feature_df = _read_optional_feature_pipeline_frame(
            _feature_pipeline_stage_path(run_dir, "feature", str(spot_id))
        )
        validation = _read_feature_pipeline_validation(
            _feature_pipeline_validation_path(run_dir, str(spot_id))
        )
        stored_df = _read_optional_feature_pipeline_frame(
            _feature_pipeline_stage_path(run_dir, "stored", str(spot_id))
        )

        status = "stored"
        if str(spot_id) not in stored_spots:
            status = "failed" if str(spot_id) in spot_errors else "skipped"

        spot_summaries.append(
            build_feature_pipeline_spot_summary(
                spot_id=str(spot_id),
                forecast_df=forecast_df,
                feature_df=feature_df,
                validation=validation,
                stored_df=stored_df,
                status=status,
                error=spot_errors.get(str(spot_id)),
            )
        )

    summary = build_feature_pipeline_run_summary(
        dataset=str(context["dataset"]),
        storage_backend=str(context["storage_backend"]),
        expected_spots=list(context.get("expected_spots", [])),
        fetched_spots=[str(spot_id) for spot_id in context.get("fetched_spots", [])],
        engineered_spots=[
            str(spot_id) for spot_id in context.get("engineered_spots", [])
        ],
        validated_spots=[
            str(spot_id) for spot_id in context.get("validated_spots", [])
        ],
        stored_spots=[str(spot_id) for spot_id in context.get("stored_spots", [])],
        stage_durations_seconds=dict(context.get("stage_durations_seconds", {})),
        stage_failure_counts=dict(context.get("stage_failure_counts", {})),
        spot_summaries=spot_summaries,
        run_status=run_status,
        error=error,
    )
    emit_feature_pipeline_run_summary(summary)


def fetch_feature_pipeline_context(
    dataset: str = "train",
    run_key: str | None = None,
) -> dict[str, object]:
    """Fetch forecasts and persist them for downstream Airflow feature tasks."""
    context = _feature_pipeline_context(dataset=dataset, run_key=run_key)
    run_dir = Path(str(context["run_dir"]))
    started_at = perf_counter()

    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    try:
        forecasts_by_spot = fetch_all_spots()
        fetched_spots: list[str] = []

        for spot_id in context["expected_spots"]:
            forecast_df = forecasts_by_spot.get(str(spot_id), pd.DataFrame())
            if forecast_df.empty:
                continue

            _write_feature_pipeline_frame(
                _feature_pipeline_stage_path(run_dir, "forecast", str(spot_id)),
                forecast_df,
            )
            fetched_spots.append(str(spot_id))

        context["fetched_spots"] = fetched_spots
        _set_feature_pipeline_stage_duration(
            context,
            stage="fetch",
            started_at=started_at,
        )
        _emit_feature_pipeline_summary(context, run_status="running")
        return context
    except Exception as exc:
        _increment_feature_pipeline_stage_failure(context, stage="fetch")
        _set_feature_pipeline_stage_duration(
            context,
            stage="fetch",
            started_at=started_at,
        )
        _emit_feature_pipeline_summary(context, run_status="failed", error=str(exc))
        raise


def engineer_feature_pipeline_context(
    feature_context: dict[str, object],
) -> dict[str, object]:
    """Engineer features from fetched forecasts for downstream Airflow tasks."""
    context = _copy_feature_pipeline_context(feature_context)
    run_dir = Path(str(context["run_dir"]))
    engineered_spots: list[str] = []
    started_at = perf_counter()

    try:
        for spot_id in context.get("fetched_spots", []):
            try:
                forecast_df = _read_feature_pipeline_frame(
                    _feature_pipeline_stage_path(run_dir, "forecast", str(spot_id))
                )
                feature_df = engineer_features(
                    forecast_df,
                    context["spot_config"][str(spot_id)]["shore_orientation_deg"],
                )
                _write_feature_pipeline_frame(
                    _feature_pipeline_stage_path(run_dir, "feature", str(spot_id)),
                    feature_df,
                )
                engineered_spots.append(str(spot_id))
            except Exception as exc:
                context["engineered_spots"] = engineered_spots
                context["spot_errors"][str(spot_id)] = str(exc)
                _increment_feature_pipeline_stage_failure(context, stage="engineer")
                _set_feature_pipeline_stage_duration(
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

        context["engineered_spots"] = engineered_spots
        _set_feature_pipeline_stage_duration(
            context,
            stage="engineer",
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
    context = _copy_feature_pipeline_context(feature_context)
    run_dir = Path(str(context["run_dir"]))
    validated_spots: list[str] = []
    started_at = perf_counter()

    try:
        for spot_id in context.get("engineered_spots", []):
            try:
                feature_df = _read_feature_pipeline_frame(
                    _feature_pipeline_stage_path(run_dir, "feature", str(spot_id))
                )
                validation = run_validation(feature_df, str(spot_id))
                _write_feature_pipeline_validation(
                    _feature_pipeline_validation_path(run_dir, str(spot_id)),
                    validation,
                )
                if not validation.is_valid:
                    raise ValueError(f"Feature validation failed for spot '{spot_id}'")
                validated_spots.append(str(spot_id))
            except Exception as exc:
                context["validated_spots"] = validated_spots
                context["spot_errors"][str(spot_id)] = str(exc)
                _increment_feature_pipeline_stage_failure(context, stage="validate")
                _set_feature_pipeline_stage_duration(
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

        context["validated_spots"] = validated_spots
        _set_feature_pipeline_stage_duration(
            context,
            stage="validate",
            started_at=started_at,
        )
        _emit_feature_pipeline_summary(context, run_status="running")
        return context
    except Exception:
        raise


def store_feature_pipeline_context(
    feature_context: dict[str, object],
) -> dict[str, object]:
    """Store validated features, emit drift metrics, and return retraining context."""
    context = _copy_feature_pipeline_context(feature_context)
    run_dir = Path(str(context["run_dir"]))
    stored_spots: list[str] = []
    drifted_spots: list[str] = []
    started_at = perf_counter()

    try:
        for spot_id in context.get("validated_spots", []):
            try:
                feature_df = _read_feature_pipeline_frame(
                    _feature_pipeline_stage_path(run_dir, "feature", str(spot_id))
                )
                previous_stored_df = _read_optional_feature_slice(
                    str(spot_id),
                    str(context["dataset"]),
                )
                write_features(
                    feature_df,
                    spot_id=str(spot_id),
                    dataset=str(context["dataset"]),
                )
                stored_df = read_features(
                    spot_id=str(spot_id),
                    dataset=str(context["dataset"]),
                )
                _write_feature_pipeline_frame(
                    _feature_pipeline_stage_path(run_dir, "stored", str(spot_id)),
                    stored_df,
                )

                if _emit_feature_drift_metrics(
                    spot_id=str(spot_id),
                    dataset=str(context["dataset"]),
                    reference_df=previous_stored_df,
                    current_df=stored_df,
                ):
                    drifted_spots.append(str(spot_id))

                stored_spots.append(str(spot_id))
            except Exception as exc:
                context["stored_spots"] = stored_spots
                context["drifted_spots"] = drifted_spots
                context["spot_errors"][str(spot_id)] = str(exc)
                _increment_feature_pipeline_stage_failure(context, stage="store")
                _set_feature_pipeline_stage_duration(
                    context,
                    stage="store",
                    started_at=started_at,
                )
                _emit_feature_pipeline_summary(
                    context,
                    run_status="failed",
                    error=str(exc),
                )
                raise

        if not stored_spots:
            context["stored_spots"] = []
            context["drifted_spots"] = []
            error = "No feature data was generated for any configured spot"
            _increment_feature_pipeline_stage_failure(context, stage="store")
            _set_feature_pipeline_stage_duration(
                context,
                stage="store",
                started_at=started_at,
            )
            _emit_feature_pipeline_summary(
                context,
                run_status="failed",
                error=error,
            )
            raise ValueError(error)

        context["stored_spots"] = stored_spots
        context["drifted_spots"] = drifted_spots
        _set_feature_pipeline_stage_duration(
            context,
            stage="store",
            started_at=started_at,
        )
        _emit_feature_pipeline_summary(context, run_status="succeeded")
        return _feature_pipeline_result(context)
    except Exception:
        raise


def _log_feature_pipeline_job_context(feature_result: dict[str, object]) -> None:
    tracking_uri = _scheduled_mlflow_tracking_uri()
    if tracking_uri is None:
        return

    mlflow.set_tracking_uri(tracking_uri)
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

    with mlflow.start_run(run_name=f"feature-{feature_result['dataset']}-refresh"):
        mlflow.log_params(
            {
                "dataset": feature_result["dataset"],
                "storage_backend": feature_result["storage_backend"],
                "stored_spots": ",".join(feature_result.get("stored_spots", [])),
                "drifted_spots": ",".join(feature_result.get("drifted_spots", [])),
            }
        )
        for name, value in metrics.items():
            mlflow.log_metric(name, value)


def store_feature_pipeline_job_context(
    feature_context: dict[str, object],
) -> dict[str, object]:
    """Store validated features and log the final Airflow-friendly refresh context."""
    result = store_feature_pipeline_context(feature_context)
    _log_feature_pipeline_job_context(result)
    return result


def _read_optional_feature_slice(spot_id: str, dataset: str) -> pd.DataFrame:
    try:
        return read_features(spot_id=spot_id, dataset=dataset)
    except FileNotFoundError:
        return pd.DataFrame()
    except Exception:
        logger.exception(
            "Failed to load prior stored features for drift monitoring on spot '%s'",
            spot_id,
        )
        return pd.DataFrame()


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


def resolve_airflow_schedule(
    schedule: str | None, *, default: str | None = None
) -> str | None:
    """Normalize an Airflow schedule string, allowing explicit opt-out values."""
    candidate = default if schedule is None else schedule
    if candidate is None:
        return None

    normalized = candidate.strip()
    if not normalized:
        return None

    if normalized.lower() in {"none", "off", "false", "manual"}:
        return None

    return normalized


def resolve_auto_retraining_mode(
    mode: str | None, *, default: str | None = "always"
) -> str | None:
    """Normalize Airflow auto-retraining mode values."""
    candidate = default if mode is None else mode
    if candidate is None:
        return None

    normalized = candidate.strip().lower()
    if not normalized or normalized in {"none", "off", "false", "manual"}:
        return None

    if normalized in {"always", "new-data", "new_data", "on-success", "on_success"}:
        return "always"

    if normalized in {"drift", "drift-only", "drift_only"}:
        return "drift"

    raise ValueError(
        "Unsupported auto retraining mode. Use 'always', 'drift', or 'off'."
    )


def should_auto_retrain(
    feature_result: dict[str, object], mode: str | None = "always"
) -> bool:
    """Return whether the Airflow feature refresh should continue into retraining."""
    resolved_mode = resolve_auto_retraining_mode(mode, default="always")
    if resolved_mode is None:
        return False

    stored_spots = [
        str(spot_id).strip()
        for spot_id in feature_result.get("stored_spots", [])
        if str(spot_id).strip()
    ]
    if resolved_mode == "always":
        return bool(stored_spots)

    return bool(feature_result.get("dataset_drift_detected", False))


def _run_feature_pipeline_result(dataset: str = "train") -> dict[str, object]:
    """Run the feature pipeline and return stored spots plus retraining context."""
    feature_context = fetch_feature_pipeline_context(dataset=dataset)
    feature_context = engineer_feature_pipeline_context(feature_context)
    feature_context = validate_feature_pipeline_context(feature_context)
    return store_feature_pipeline_context(feature_context)


def run_feature_pipeline(dataset: str = "train") -> list[str]:
    """Fetch, engineer, validate, store, and monitor features for all spots."""
    return list(_run_feature_pipeline_result(dataset=dataset)["stored_spots"])


def _scheduled_mlflow_tracking_uri() -> str | None:
    tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "").strip()
    return tracking_uri or None


def run_feature_pipeline_job(dataset: str = "train") -> list[str]:
    """Run the feature pipeline and optionally log a refresh run to MLflow."""
    tracking_uri = _scheduled_mlflow_tracking_uri()
    if tracking_uri is None:
        return run_feature_pipeline(dataset=dataset)

    mlflow.set_tracking_uri(tracking_uri)
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


def run_feature_pipeline_job_context(dataset: str = "train") -> dict[str, object]:
    """Run the feature pipeline and return Airflow-friendly retraining context."""
    result = _run_feature_pipeline_result(dataset=dataset)
    _log_feature_pipeline_job_context(result)
    return result


def _training_summary_state(
    *,
    dataset: str,
    requested_stage: str,
    training_run_id: str | None = None,
) -> dict[str, Any]:
    try:
        summary = read_training_pipeline_run_summary(dataset)
    except FileNotFoundError:
        summary = {}

    if training_run_id and summary.get("training_run_id") not in {None, training_run_id}:
        summary = {}

    return {
        "dataset": dataset,
        "requested_stage": requested_stage,
        "training_run_id": training_run_id or summary.get("training_run_id"),
        "stage_durations_seconds": dict(summary.get("stage_durations_seconds", {})),
        "stage_failure_counts": {
            stage: int(dict(summary.get("stage_failure_counts", {})).get(stage, 0))
            for stage in TRAINING_PIPELINE_STAGES
        },
        "training_row_count": summary.get("training_row_count"),
        "training_feature_count": summary.get("training_feature_count"),
        "train_row_count": summary.get("train_row_count"),
        "test_row_count": summary.get("test_row_count"),
        "evaluation_report_path": summary.get("evaluation_report_path"),
        "evaluation_report_exists": bool(summary.get("evaluation_report_exists", False)),
        "registered_model_name": summary.get("registered_model_name"),
        "registered_model_version": summary.get("registered_model_version"),
        "run_metrics": {
            str(name): float(value)
            for name, value in dict(summary.get("run_metrics", {})).items()
        },
    }


def _set_training_pipeline_stage_duration(
    training_state: dict[str, Any],
    *,
    stage: str,
    started_at: float,
) -> None:
    durations = dict(training_state.get("stage_durations_seconds", {}))
    durations[str(stage)] = float(perf_counter() - started_at)
    training_state["stage_durations_seconds"] = durations


def _increment_training_pipeline_stage_failure(
    training_state: dict[str, Any],
    *,
    stage: str,
) -> None:
    counts = {
        known_stage: int(
            dict(training_state.get("stage_failure_counts", {})).get(known_stage, 0)
        )
        for known_stage in TRAINING_PIPELINE_STAGES
    }
    counts[str(stage)] = int(counts.get(str(stage), 0)) + 1
    training_state["stage_failure_counts"] = counts


def _emit_training_summary(
    training_state: dict[str, Any],
    *,
    run_status: str,
    error: str | None = None,
) -> None:
    summary = build_training_pipeline_run_summary(
        dataset=str(training_state["dataset"]),
        requested_stage=str(training_state["requested_stage"]),
        training_run_id=(
            None
            if training_state.get("training_run_id") is None
            else str(training_state["training_run_id"])
        ),
        stage_durations_seconds=dict(training_state.get("stage_durations_seconds", {})),
        stage_failure_counts=dict(training_state.get("stage_failure_counts", {})),
        run_status=run_status,
        run_metrics=dict(training_state.get("run_metrics", {})),
        training_row_count=training_state.get("training_row_count"),
        training_feature_count=training_state.get("training_feature_count"),
        train_row_count=training_state.get("train_row_count"),
        test_row_count=training_state.get("test_row_count"),
        evaluation_report_path=training_state.get("evaluation_report_path"),
        evaluation_report_exists=bool(training_state.get("evaluation_report_exists", False)),
        registered_model_name=training_state.get("registered_model_name"),
        registered_model_version=(
            None
            if training_state.get("registered_model_version") is None
            else str(training_state["registered_model_version"])
        ),
        error=error,
    )
    emit_training_pipeline_run_summary(summary)


def _training_run_snapshot(training_run_id: str) -> dict[str, Any]:
    run = mlflow.MlflowClient().get_run(training_run_id)
    metrics = {str(name): float(value) for name, value in dict(run.data.metrics).items()}
    params = {str(name): str(value) for name, value in dict(run.data.params).items()}

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


def run_training_pipeline_step(
    dataset: str = "train",
    requested_stage: str = "Candidate",
) -> str:
    """Train the model and persist the latest step-level training summary."""
    training_state = _training_summary_state(
        dataset=dataset,
        requested_stage=requested_stage,
    )
    started_at = perf_counter()

    try:
        training_run_id = run_training_pipeline(dataset=dataset)
        training_state.update(
            _training_run_snapshot(training_run_id),
        )
        training_state["training_run_id"] = training_run_id
        _set_training_pipeline_stage_duration(
            training_state,
            stage="train",
            started_at=started_at,
        )
        _emit_training_summary(training_state, run_status="running")
        return training_run_id
    except Exception as exc:
        _increment_training_pipeline_stage_failure(training_state, stage="train")
        _set_training_pipeline_stage_duration(
            training_state,
            stage="train",
            started_at=started_at,
        )
        _emit_training_summary(training_state, run_status="failed", error=str(exc))
        raise


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
    started_at = perf_counter()

    try:
        mlflow.set_tracking_uri(get_mlflow_tracking_uri())
        run = mlflow.MlflowClient().get_run(training_run_id)
        metrics = {str(name): float(value) for name, value in dict(run.data.metrics).items()}
        if not metrics:
            raise ValueError(f"No evaluation metrics found for run '{training_run_id}'")

        report_dir = project_root() / "airflow" / "reports"
        report_path = report_dir / f"evaluation-{training_run_id}.md"

        with mlflow.start_run(run_id=training_run_id):
            resolved_report_path = generate_evaluation_report(metrics, str(report_path))

        training_state["training_run_id"] = training_run_id
        training_state["run_metrics"] = metrics
        training_state["evaluation_report_path"] = resolved_report_path
        training_state["evaluation_report_exists"] = Path(resolved_report_path).exists()
        _set_training_pipeline_stage_duration(
            training_state,
            stage="evaluate",
            started_at=started_at,
        )
        _emit_training_summary(training_state, run_status="running")
        return resolved_report_path
    except Exception as exc:
        _increment_training_pipeline_stage_failure(training_state, stage="evaluate")
        _set_training_pipeline_stage_duration(
            training_state,
            stage="evaluate",
            started_at=started_at,
        )
        _emit_training_summary(training_state, run_status="failed", error=str(exc))
        raise


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
    started_at = perf_counter()

    try:
        model_version = register_model(training_run_id)
        promote_model(None, model_version.version, stage=stage)
        training_state["training_run_id"] = training_run_id
        training_state["registered_model_name"] = get_mlflow_config()["model_name"]
        training_state["registered_model_version"] = str(model_version.version)
        _set_training_pipeline_stage_duration(
            training_state,
            stage="register",
            started_at=started_at,
        )
        _emit_training_summary(training_state, run_status="succeeded")
        return str(model_version.version)
    except Exception as exc:
        _increment_training_pipeline_stage_failure(training_state, stage="register")
        _set_training_pipeline_stage_duration(
            training_state,
            stage="register",
            started_at=started_at,
        )
        _emit_training_summary(training_state, run_status="failed", error=str(exc))
        raise
