"""Drift detection helpers backed by Evidently and StatsD."""

from __future__ import annotations

import json
import logging
import re
import socket
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from foehncast._report_store import (
    ReportLocation,
    read_json_object,
    report_json_paths,
    report_object_path,
    write_json_object,
)
from foehncast.config import get_monitoring_config
from foehncast.env import env_value
from foehncast.monitoring._common import safe_float
from foehncast.monitoring.pipeline_metrics import configured_pipeline_report_dir

_DEFAULT_DRIFT_THRESHOLD = 0.15
_DEFAULT_EVALUATION_WINDOW_DAYS = 30
_DEFAULT_STATSD_HOST = "127.0.0.1"
_DEFAULT_STATSD_PORT = 8125
_DEFAULT_STATSD_PREFIX = "drift_metrics"
_PREDICTION_TIME_COLUMNS = (
    "prediction_timestamp",
    "timestamp",
    "created_at",
    "event_time",
    "time",
)
_PREDICTION_PRIORITY_COLUMNS = (
    "prediction",
    "predicted_quality_index",
    "quality_index",
    "score",
)
_PREDICTION_EXCLUDED_COLUMNS = {
    "spot_id",
    "model_version",
    "request_id",
    "user_id",
    "session_id",
}


@dataclass(frozen=True)
class DriftMetric:
    """Column-level drift result extracted from Evidently output."""

    column_name: str
    drift_score: float | None
    drift_detected: bool
    threshold: float | None = None
    method: str | None = None


@dataclass(frozen=True)
class DriftReport:
    """Stable drift report contract used by monitoring and tests."""

    report_kind: str
    dataset_name: str
    dataset_version: str
    threshold: float
    reference_row_count: int
    current_row_count: int
    column_count: int
    drifted_column_count: int
    share_of_drifted_columns: float
    dataset_drift: bool
    generated_at: str
    metrics: tuple[DriftMetric, ...]
    raw_metrics: tuple[dict[str, Any], ...] = ()


def detect_data_drift(
    reference_df: pd.DataFrame,
    current_df: pd.DataFrame,
    threshold: float | None = None,
) -> DriftReport:
    """Detect drift between two feature datasets."""
    dataset_name, dataset_version = _report_identity(
        current_df,
        default_name="data",
        default_version="v1",
    )
    reference_frame, current_frame = _prepare_drift_frames(reference_df, current_df)
    resolved_threshold = _resolved_drift_threshold(threshold)
    return _build_drift_report(
        report_kind="data",
        dataset_name=dataset_name,
        dataset_version=dataset_version,
        reference_frame=reference_frame,
        current_frame=current_frame,
        threshold=resolved_threshold,
    )


def detect_prediction_drift(predictions_log: pd.DataFrame) -> DriftReport:
    """Detect drift in logged predictions between reference and recent windows."""
    if predictions_log.empty:
        raise ValueError("Prediction log must not be empty")

    dataset_name, dataset_version = _report_identity(
        predictions_log,
        default_name="prediction",
        default_version="v1",
    )

    reference_frame, current_frame = _split_prediction_log(
        predictions_log, _resolved_evaluation_window_days()
    )
    selected_columns = _prediction_columns(reference_frame, current_frame)
    if not selected_columns:
        raise ValueError(
            "Prediction log does not contain comparable prediction columns"
        )

    return _build_drift_report(
        report_kind="prediction",
        dataset_name=dataset_name,
        dataset_version=dataset_version,
        reference_frame=reference_frame[selected_columns].copy(),
        current_frame=current_frame[selected_columns].copy(),
        threshold=_resolved_drift_threshold(),
    )


def push_drift_metrics(report: DriftReport) -> None:
    """Push drift metrics to StatsD and persist for Prometheus scraping."""
    _persist_drift_report(report)

    host = env_value("FOEHNCAST_STATSD_HOST") or _DEFAULT_STATSD_HOST
    port = int(env_value("FOEHNCAST_STATSD_PORT") or str(_DEFAULT_STATSD_PORT))
    prefix = env_value("FOEHNCAST_STATSD_PREFIX") or _DEFAULT_STATSD_PREFIX

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
            for line in _statsd_lines(report, prefix or _DEFAULT_STATSD_PREFIX):
                client.sendto(
                    line.encode("utf-8"), (host or _DEFAULT_STATSD_HOST, port)
                )
    except OSError:
        logging.getLogger(__name__).debug("StatsD push failed (expected in cloud)")


def _drift_report_dir() -> ReportLocation:
    """Return the directory for persisted drift reports (gs:// or local)."""
    return configured_pipeline_report_dir()


def _drift_report_path(report_kind: str, dataset_name: str) -> ReportLocation:
    return report_object_path(
        _drift_report_dir(),
        f"drift-{report_kind}-{dataset_name}-latest.json",
    )


def _persist_drift_report(report: DriftReport) -> None:
    """Write drift report to a JSON file for Prometheus export."""
    path = _drift_report_path(report.report_kind, report.dataset_name)
    payload = json.loads(json.dumps(asdict(report), default=str))
    write_json_object(path, payload)


def read_drift_report(report_kind: str, dataset_name: str) -> dict[str, Any] | None:
    """Read a persisted drift report, or None if not available."""
    path = _drift_report_path(report_kind, dataset_name)
    try:
        return read_json_object(
            path,
            error_message="Drift report must decode to a JSON object.",
        )
    except (FileNotFoundError, ValueError, OSError):
        return None


def read_all_drift_reports() -> list[dict[str, Any]]:
    """Read all persisted drift reports from the report directory."""
    try:
        paths = report_json_paths(_drift_report_dir(), "drift-*-latest.json")
    except OSError:
        return []
    reports: list[dict[str, Any]] = []
    for path in paths:
        try:
            reports.append(
                read_json_object(
                    path,
                    error_message="Drift report must decode to a JSON object.",
                )
            )
        except (FileNotFoundError, ValueError, OSError):
            continue
    return reports


def _build_drift_report(
    *,
    report_kind: str,
    dataset_name: str,
    dataset_version: str,
    reference_frame: pd.DataFrame,
    current_frame: pd.DataFrame,
    threshold: float,
) -> DriftReport:
    raw_metrics = tuple(
        _run_evidently_data_drift(reference_frame, current_frame, threshold)
    )
    metrics, drifted_column_count, share_of_drifted_columns = _parse_column_metrics(
        raw_metrics, len(reference_frame.columns)
    )

    return DriftReport(
        report_kind=report_kind,
        dataset_name=dataset_name,
        dataset_version=dataset_version,
        threshold=threshold,
        reference_row_count=int(len(reference_frame)),
        current_row_count=int(len(current_frame)),
        column_count=int(len(reference_frame.columns)),
        drifted_column_count=drifted_column_count,
        share_of_drifted_columns=share_of_drifted_columns,
        dataset_drift=share_of_drifted_columns >= threshold,
        generated_at=datetime.now(UTC).isoformat(),
        metrics=metrics,
        raw_metrics=raw_metrics,
    )


def _run_evidently_data_drift(
    reference_frame: pd.DataFrame,
    current_frame: pd.DataFrame,
    threshold: float,
) -> list[dict[str, Any]]:
    report_class, drift_preset_class = _evidently_classes()
    snapshot = report_class([drift_preset_class(drift_share=threshold)]).run(
        current_data=current_frame,
        reference_data=reference_frame,
    )
    return list(snapshot.dict().get("metrics", []))


def _evidently_classes() -> tuple[Any, Any]:
    try:
        from evidently import Report
        from evidently.presets import DataDriftPreset
    except ImportError as exc:  # pragma: no cover - guarded by dependency setup
        raise RuntimeError(
            "Evidently is required for drift detection. Install the 'evidently' package."
        ) from exc

    return Report, DataDriftPreset


def _prepare_drift_frames(
    reference_df: pd.DataFrame,
    current_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if reference_df.empty or current_df.empty:
        raise ValueError("Reference and current datasets must not be empty")

    common_columns = [
        column for column in reference_df.columns if column in current_df.columns
    ]
    if not common_columns:
        raise ValueError("Reference and current datasets share no comparable columns")

    return (
        reference_df[common_columns].copy().reset_index(drop=True),
        current_df[common_columns].copy().reset_index(drop=True),
    )


def _report_identity(
    frame: pd.DataFrame,
    *,
    default_name: str,
    default_version: str,
) -> tuple[str, str]:
    attrs = getattr(frame, "attrs", {}) or {}
    dataset_name = str(attrs.get("dataset_name", "")).strip() or default_name
    dataset_version = str(attrs.get("dataset_version", "")).strip() or default_version
    return dataset_name, dataset_version


def _resolved_drift_threshold(threshold: float | None = None) -> float:
    if threshold is not None:
        return float(threshold)

    monitoring_config = get_monitoring_config()
    return float(monitoring_config.get("drift_threshold", _DEFAULT_DRIFT_THRESHOLD))


def _resolved_evaluation_window_days() -> int:
    monitoring_config = get_monitoring_config()
    return int(
        monitoring_config.get(
            "evaluation_window_days",
            _DEFAULT_EVALUATION_WINDOW_DAYS,
        )
    )


def _prediction_time_column(frame: pd.DataFrame) -> str | None:
    for column in _PREDICTION_TIME_COLUMNS:
        if column in frame.columns:
            return column
    return None


def _split_prediction_log(
    predictions_log: pd.DataFrame,
    evaluation_window_days: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if len(predictions_log) < 2:
        raise ValueError("Prediction log must contain at least two rows")

    time_column = _prediction_time_column(predictions_log)
    if time_column is not None:
        timestamps = pd.to_datetime(
            predictions_log[time_column], errors="coerce", utc=True
        )
        valid_rows = timestamps.notna()
        if valid_rows.any():
            ordered = predictions_log.loc[valid_rows].copy()
            ordered[time_column] = timestamps.loc[valid_rows]
            ordered = ordered.sort_values(time_column).reset_index(drop=True)
            cutoff = ordered[time_column].max() - pd.Timedelta(
                days=evaluation_window_days
            )
            reference_frame = ordered.loc[ordered[time_column] < cutoff]
            current_frame = ordered.loc[ordered[time_column] >= cutoff]
            if not reference_frame.empty and not current_frame.empty:
                return reference_frame.reset_index(
                    drop=True
                ), current_frame.reset_index(drop=True)

    midpoint = len(predictions_log) // 2
    if midpoint == 0 or midpoint == len(predictions_log):
        raise ValueError("Prediction log must contain two comparable windows")

    ordered = predictions_log.reset_index(drop=True)
    return ordered.iloc[:midpoint].copy(), ordered.iloc[midpoint:].copy()


def _prediction_columns(
    reference_frame: pd.DataFrame,
    current_frame: pd.DataFrame,
) -> list[str]:
    common_columns = [
        column
        for column in reference_frame.columns
        if column in current_frame.columns
        and column not in _PREDICTION_EXCLUDED_COLUMNS
        and column not in _PREDICTION_TIME_COLUMNS
        and not column.endswith("_id")
    ]
    preferred = [
        column
        for column in common_columns
        if column in _PREDICTION_PRIORITY_COLUMNS or "prediction" in column.lower()
    ]
    if preferred:
        return preferred

    return [
        column
        for column in common_columns
        if pd.api.types.is_numeric_dtype(reference_frame[column])
        or pd.api.types.is_bool_dtype(reference_frame[column])
        or pd.api.types.is_string_dtype(reference_frame[column])
        or pd.api.types.is_object_dtype(reference_frame[column])
    ]


def _parse_column_metrics(
    raw_metrics: tuple[dict[str, Any], ...],
    column_count: int,
) -> tuple[tuple[DriftMetric, ...], int, float]:
    drifted_column_count: int | None = None
    share_of_drifted_columns: float | None = None
    column_metrics: list[DriftMetric] = []

    # Evidently 0.7 emits a flat metric list rather than the older nested result object.
    for metric in raw_metrics:
        config = metric.get("config", {})
        metric_type = str(config.get("type", ""))
        value = metric.get("value")

        if metric_type.endswith(":DriftedColumnsCount") and isinstance(value, dict):
            drifted_column_count = int(float(value.get("count", 0.0)))
            share_of_drifted_columns = float(value.get("share", 0.0))
            continue

        if not metric_type.endswith(":ValueDrift"):
            continue

        score = safe_float(value)
        threshold = safe_float(config.get("threshold"))
        method = str(config.get("method", "")).strip() or None
        column_metrics.append(
            DriftMetric(
                column_name=str(config.get("column", "unknown")),
                drift_score=score,
                drift_detected=_is_drift_detected(score, threshold, method),
                threshold=threshold,
                method=method,
            )
        )

    if drifted_column_count is None:
        drifted_column_count = sum(metric.drift_detected for metric in column_metrics)
    if share_of_drifted_columns is None:
        divisor = column_count or len(column_metrics) or 1
        share_of_drifted_columns = float(drifted_column_count / divisor)

    return tuple(column_metrics), drifted_column_count, share_of_drifted_columns


def _is_drift_detected(
    score: float | None,
    threshold: float | None,
    method: str | None,
) -> bool:
    if score is None or threshold is None:
        return False

    normalized_method = (method or "").lower()
    if "p_value" in normalized_method or "p-value" in normalized_method:
        return score <= threshold
    return score >= threshold


def _statsd_lines(report: DriftReport, prefix: str) -> list[str]:
    dataset_name = _sanitize_metric_segment(report.dataset_name)
    dataset_version = _sanitize_metric_segment(report.dataset_version)

    dataset_metrics = [
        ("threshold", report.threshold),
        ("drifted_column_count", float(report.drifted_column_count)),
        ("share_of_drifted_columns", report.share_of_drifted_columns),
        ("dataset_drift", float(report.dataset_drift)),
    ]
    lines = [
        _statsd_line(prefix, dataset_name, dataset_version, "dataset", name, value)
        for name, value in dataset_metrics
    ]

    for metric in report.metrics:
        column_name = _sanitize_metric_segment(metric.column_name)
        lines.append(
            _statsd_line(
                prefix,
                dataset_name,
                dataset_version,
                column_name,
                "drift_detected",
                float(metric.drift_detected),
            )
        )
        if metric.drift_score is not None:
            lines.append(
                _statsd_line(
                    prefix,
                    dataset_name,
                    dataset_version,
                    column_name,
                    "drift_score",
                    metric.drift_score,
                )
            )
        if metric.threshold is not None:
            lines.append(
                _statsd_line(
                    prefix,
                    dataset_name,
                    dataset_version,
                    column_name,
                    "threshold",
                    metric.threshold,
                )
            )

    return lines


def _statsd_line(
    prefix: str,
    dataset_name: str,
    dataset_version: str,
    column_name: str,
    metric_name: str,
    value: float,
) -> str:
    return (
        f"{_sanitize_metric_segment(prefix)}.{dataset_name}.{dataset_version}."
        f"{column_name}.{_sanitize_metric_segment(metric_name)}:{value}|g"
    )


def _sanitize_metric_segment(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")
    return sanitized or "unknown"


__all__ = [
    "DriftMetric",
    "DriftReport",
    "detect_data_drift",
    "detect_prediction_drift",
    "push_drift_metrics",
    "read_all_drift_reports",
    "read_drift_report",
]
