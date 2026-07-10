"""Shared constants and helpers for the prediction log subsystem."""

from __future__ import annotations

import json
import logging
from typing import Any

import pandas as pd

from foehncast.config import get_monitoring_config
from foehncast.env import env_value

logger = logging.getLogger(__name__)

_DEFAULT_PREDICTION_LOG_MAX_ROWS = 2048
_DEFAULT_PREDICTION_LOG_RETENTION_DAYS = 60
_DEFAULT_BIGQUERY_PARTITION_GRANULARITY = "DAY"
_DEFAULT_PREDICTION_EVENT_CLUSTER_FIELDS = ("model_version", "endpoint", "spot_id")


def _normalized_requested_spot_ids(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]

    if value is None:
        return []

    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
        return [item.strip() for item in stripped.split(",") if item.strip()]

    if pd.isna(value):
        return []

    return [str(value).strip()] if str(value).strip() else []


def _normalized_prediction_frame(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    for column in ("prediction_timestamp", "forecast_time"):
        if column in normalized.columns:
            normalized[column] = pd.to_datetime(
                normalized[column],
                errors="coerce",
                utc=True,
            )

    if "requested_spot_ids" in normalized.columns:
        normalized["requested_spot_ids"] = normalized["requested_spot_ids"].apply(
            _normalized_requested_spot_ids
        )

    return normalized


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
