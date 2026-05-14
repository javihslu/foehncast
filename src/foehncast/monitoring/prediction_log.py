"""Prediction-event persistence and model-side drift monitoring helpers.

The monitoring stack uses two related JSONL contracts:

- ``prediction-log.jsonl`` is a bounded local working set used for request-side
    drift evaluation.
- ``prediction-events.jsonl`` is the durable event history contract used by
    monitoring readers and can be redirected to shared storage with an env var.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from foehncast.config import get_monitoring_config
from foehncast.env import env_value
from foehncast.monitoring.drift import (
    DriftReport,
    detect_prediction_drift,
    push_drift_metrics,
)
from foehncast.paths import project_root

logger = logging.getLogger(__name__)

PREDICTION_EVENT_FIELDS = (
    "prediction_timestamp",
    "forecast_time",
    "quality_index",
    "endpoint",
    "model_version",
    "spot_id",
    "spot_name",
    "requested_spot_ids",
)
_DEFAULT_PREDICTION_LOG_MAX_ROWS = 2048
_DEFAULT_PREDICTION_LOG_RETENTION_DAYS = 60


def _default_prediction_log_path() -> Path:
    return project_root() / ".state" / "monitoring" / "prediction-log.jsonl"


def prediction_event_log_path(
    path: Path | None = None,
    *,
    fallback_log_path: Path | None = None,
) -> Path:
    if path is not None:
        return path

    raw_value = env_value("FOEHNCAST_PREDICTION_EVENT_LOG_PATH")
    if raw_value:
        return Path(raw_value).expanduser()

    if fallback_log_path is not None:
        return fallback_log_path.with_name("prediction-events.jsonl")

    return project_root() / ".state" / "monitoring" / "prediction-events.jsonl"


def _prediction_log_max_rows(configured: int | None = None) -> int:
    if configured is not None:
        return max(int(configured), 2)

    raw_value = env_value("FOEHNCAST_PREDICTION_LOG_MAX_ROWS") or str(
        _DEFAULT_PREDICTION_LOG_MAX_ROWS
    )
    try:
        parsed = int(raw_value)
    except ValueError:
        logger.warning(
            "Invalid FOEHNCAST_PREDICTION_LOG_MAX_ROWS=%r; using %s",
            raw_value,
            _DEFAULT_PREDICTION_LOG_MAX_ROWS,
        )
        return _DEFAULT_PREDICTION_LOG_MAX_ROWS

    return max(parsed, 2)


def _prediction_log_lines(source: Path) -> list[str]:
    return [
        line for line in source.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _append_prediction_rows(destination: Path, rows: list[dict[str, Any]]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)

    with destination.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def _prediction_log_retention_days(configured: int | None = None) -> int:
    if configured is not None:
        return max(int(configured), 1)

    monitoring_config = get_monitoring_config()
    evaluation_window_days = max(
        int(monitoring_config.get("evaluation_window_days", 30)),
        1,
    )
    configured_retention_days = int(
        monitoring_config.get(
            "prediction_log_retention_days",
            _DEFAULT_PREDICTION_LOG_RETENTION_DAYS,
        )
    )
    return max(configured_retention_days, evaluation_window_days * 2)


def _normalized_model_version(value: Any) -> str:
    return str(value or "unknown").strip() or "unknown"


def _retained_prediction_log_lines(
    lines: list[str],
    *,
    max_rows: int,
    retention_days: int,
    model_version: str | None = None,
) -> list[str]:
    entries: list[dict[str, Any]] = []
    valid_timestamps: list[pd.Timestamp] = []

    for index, line in enumerate(lines):
        record = json.loads(line)
        prediction_timestamp = pd.to_datetime(
            record.get("prediction_timestamp"),
            errors="coerce",
            utc=True,
        )
        if pd.notna(prediction_timestamp):
            valid_timestamps.append(prediction_timestamp)
        entries.append(
            {
                "index": index,
                "line": line,
                "model_version": _normalized_model_version(record.get("model_version")),
                "prediction_timestamp": prediction_timestamp,
            }
        )

    if valid_timestamps:
        cutoff = max(valid_timestamps) - pd.Timedelta(days=retention_days)
        entries = [
            entry
            for entry in entries
            if pd.notna(entry["prediction_timestamp"])
            and entry["prediction_timestamp"] >= cutoff
        ]

    if model_version is not None:
        normalized_model_version = _normalized_model_version(model_version)
        return [
            entry["line"]
            for entry in entries
            if entry["model_version"] == normalized_model_version
        ][-max_rows:]

    retained_indices_by_model: dict[str, list[int]] = {}

    for entry in entries:
        indices = retained_indices_by_model.setdefault(entry["model_version"], [])
        indices.append(entry["index"])
        if len(indices) > max_rows:
            indices.pop(0)

    retained_indices = {
        index for indices in retained_indices_by_model.values() for index in indices
    }
    return [entry["line"] for entry in entries if entry["index"] in retained_indices]


def _trim_prediction_log(
    source: Path,
    *,
    max_rows: int,
    retention_days: int,
) -> None:
    lines = _prediction_log_lines(source)
    retained_lines = _retained_prediction_log_lines(
        lines,
        max_rows=max_rows,
        retention_days=retention_days,
    )

    if retained_lines == lines:
        return

    source.write_text(
        "".join(f"{line}\n" for line in retained_lines),
        encoding="utf-8",
    )


def _flatten_prediction_payload(
    prediction_payload: dict[str, Any],
    *,
    endpoint: str,
    spot_ids: list[str] | None = None,
    logged_at: datetime | None = None,
) -> list[dict[str, Any]]:
    resolved_timestamp = (logged_at or datetime.now(UTC)).isoformat()
    model_version = _normalized_model_version(prediction_payload.get("model_version"))
    requested_spot_ids = list(spot_ids or [])
    rows: list[dict[str, Any]] = []

    for prediction in prediction_payload.get("predictions", []):
        for forecast in prediction.get("forecast", []):
            row = {
                "prediction_timestamp": resolved_timestamp,
                "forecast_time": forecast.get("time"),
                "quality_index": float(forecast["quality_index"]),
                "endpoint": endpoint,
                "model_version": model_version,
                "spot_id": prediction.get("spot_id"),
                "spot_name": prediction.get("spot_name"),
                "requested_spot_ids": requested_spot_ids,
            }
            rows.append({field: row[field] for field in PREDICTION_EVENT_FIELDS})

    return rows


def _read_prediction_rows(
    source: Path,
    *,
    max_rows: int | None = None,
    model_version: str | None = None,
    retention_days: int | None = None,
) -> pd.DataFrame:
    if not source.exists():
        return pd.DataFrame()

    lines = _retained_prediction_log_lines(
        _prediction_log_lines(source),
        max_rows=_prediction_log_max_rows(max_rows),
        retention_days=_prediction_log_retention_days(retention_days),
        model_version=model_version,
    )

    rows = [json.loads(line) for line in lines]
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame

    for column in ("prediction_timestamp", "forecast_time"):
        if column in frame.columns:
            frame[column] = pd.to_datetime(frame[column], errors="coerce", utc=True)

    return frame


def append_prediction_log(
    prediction_payload: dict[str, Any],
    *,
    endpoint: str,
    spot_ids: list[str] | None = None,
    path: Path | None = None,
    event_path: Path | None = None,
    logged_at: datetime | None = None,
    max_rows: int | None = None,
    retention_days: int | None = None,
) -> Path | None:
    rows = _flatten_prediction_payload(
        prediction_payload,
        endpoint=endpoint,
        spot_ids=spot_ids,
        logged_at=logged_at,
    )
    if not rows:
        return None

    destination = path or _default_prediction_log_path()
    durable_destination = prediction_event_log_path(
        event_path,
        fallback_log_path=destination,
    )

    if durable_destination == destination:
        logger.warning(
            "Prediction event history path %s matches the retained working log; "
            "using a sibling prediction-events.jsonl file instead.",
            durable_destination,
        )
        durable_destination = destination.with_name("prediction-events.jsonl")

    _append_prediction_rows(durable_destination, rows)
    _append_prediction_rows(destination, rows)

    _trim_prediction_log(
        destination,
        max_rows=_prediction_log_max_rows(max_rows),
        retention_days=_prediction_log_retention_days(retention_days),
    )

    return destination


def read_prediction_log(
    path: Path | None = None,
    *,
    max_rows: int | None = None,
    model_version: str | None = None,
    retention_days: int | None = None,
) -> pd.DataFrame:
    source = path or _default_prediction_log_path()
    return _read_prediction_rows(
        source,
        max_rows=max_rows,
        model_version=model_version,
        retention_days=retention_days,
    )


def read_prediction_event_log(
    path: Path | None = None,
    *,
    fallback_log_path: Path | None = None,
    max_rows: int | None = None,
    model_version: str | None = None,
    retention_days: int | None = None,
) -> pd.DataFrame:
    source = prediction_event_log_path(path, fallback_log_path=fallback_log_path)
    return _read_prediction_rows(
        source,
        max_rows=max_rows,
        model_version=model_version,
        retention_days=retention_days,
    )


def read_prediction_history(
    event_path: Path | None = None,
    *,
    fallback_log_path: Path | None = None,
    max_rows: int | None = None,
    model_version: str | None = None,
    retention_days: int | None = None,
) -> pd.DataFrame:
    source = prediction_event_log_path(
        event_path,
        fallback_log_path=fallback_log_path,
    )
    if source.exists():
        return _read_prediction_rows(
            source,
            max_rows=max_rows,
            model_version=model_version,
            retention_days=retention_days,
        )

    return read_prediction_log(
        fallback_log_path,
        max_rows=max_rows,
        model_version=model_version,
        retention_days=retention_days,
    )


def emit_prediction_drift_metrics(
    prediction_payload: dict[str, Any],
    *,
    endpoint: str,
    spot_ids: list[str] | None = None,
    path: Path | None = None,
    event_path: Path | None = None,
    max_rows: int | None = None,
    retention_days: int | None = None,
) -> DriftReport | None:
    try:
        model_version = _normalized_model_version(
            prediction_payload.get("model_version")
        )
        log_path = append_prediction_log(
            prediction_payload,
            endpoint=endpoint,
            spot_ids=spot_ids,
            path=path,
            event_path=event_path,
            max_rows=max_rows,
            retention_days=retention_days,
        )
        if log_path is None:
            return None

        predictions_log = read_prediction_history(
            event_path,
            fallback_log_path=log_path,
            max_rows=max_rows,
            model_version=model_version,
            retention_days=retention_days,
        )
        if predictions_log.empty:
            return None

        if len(predictions_log) < 2:
            return None

        predictions_log.attrs.update(
            {
                "dataset_name": "inference_predictions",
                "dataset_version": model_version,
            }
        )
        report = detect_prediction_drift(predictions_log)
        push_drift_metrics(report)
        return report
    except Exception:
        logger.exception(
            "Failed to append prediction log or emit prediction drift metrics"
        )
        return None


__all__ = [
    "PREDICTION_EVENT_FIELDS",
    "append_prediction_log",
    "emit_prediction_drift_metrics",
    "prediction_event_log_path",
    "read_prediction_event_log",
    "read_prediction_history",
    "read_prediction_log",
]
