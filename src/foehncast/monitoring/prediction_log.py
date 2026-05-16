"""Prediction-event persistence and model-side drift monitoring helpers.

The monitoring stack uses two related JSONL contracts:

- ``prediction-log.jsonl`` is a bounded local working set used for request-side
    drift evaluation.
- ``prediction-events.jsonl`` is the durable event history contract used by
    monitoring readers and can be redirected to shared storage with an env var.

Only ``prediction-events.jsonl`` is a history source. The bounded working log is
written alongside it for local inspection and trimming, but readers do not fall
back to it when the durable event contract is missing.
"""

from __future__ import annotations

from datetime import UTC, datetime
import importlib
import json
import logging
from pathlib import Path
import types
from typing import Any

import pandas as pd

from foehncast.config import get_monitoring_config, get_storage_config
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
_DEFAULT_BIGQUERY_PARTITION_GRANULARITY = "DAY"
_DEFAULT_PREDICTION_EVENT_CLUSTER_FIELDS = ("model_version", "endpoint", "spot_id")


def _default_prediction_log_path() -> Path:
    return project_root() / ".state" / "monitoring" / "prediction-log.jsonl"


def _prediction_event_storage_backend(storage_config: dict[str, Any]) -> str:
    backend = str(storage_config.get("backend", "")).strip()
    if backend not in {"s3", "bigquery"}:
        raise ValueError(f"Unsupported storage backend: {backend}")
    return backend


def prediction_event_log_path(path: Path | None = None) -> Path:
    if path is not None:
        return path

    raw_value = env_value("FOEHNCAST_PREDICTION_EVENT_LOG_PATH")
    if raw_value:
        return Path(raw_value).expanduser()

    return project_root() / ".state" / "monitoring" / "prediction-events.jsonl"


def _prediction_event_write_path(
    path: Path | None = None,
    *,
    working_log_path: Path | None = None,
) -> Path:
    if path is not None:
        return path

    raw_value = env_value("FOEHNCAST_PREDICTION_EVENT_LOG_PATH")
    if raw_value:
        return Path(raw_value).expanduser()

    if working_log_path is not None:
        return working_log_path.with_name("prediction-events.jsonl")

    return project_root() / ".state" / "monitoring" / "prediction-events.jsonl"


def _bigquery_module() -> Any:
    return importlib.import_module("google.cloud.bigquery")


def _google_exceptions_module() -> Any:
    return importlib.import_module("google.api_core.exceptions")


def _prediction_event_bigquery_contract(
    storage_config: dict[str, Any],
) -> dict[str, Any]:
    warehouse_contracts = storage_config.get("warehouse_contracts", {})
    raw_contract = {}
    if isinstance(warehouse_contracts, dict):
        candidate = warehouse_contracts.get("prediction_events", {})
        if isinstance(candidate, dict):
            raw_contract = candidate

    dataset = str(raw_contract.get("dataset", "")).strip()
    if not dataset:
        raise ValueError(
            "Prediction-event warehouse contract requires a BigQuery dataset"
        )

    table = str(raw_contract.get("table", "")).strip()
    if not table:
        raise ValueError(
            "Prediction-event warehouse contract requires a BigQuery table"
        )

    cluster_fields = raw_contract.get(
        "cluster_fields",
        _DEFAULT_PREDICTION_EVENT_CLUSTER_FIELDS,
    )
    resolved_cluster_fields = [
        str(field).strip() for field in cluster_fields if str(field).strip()
    ]
    if not resolved_cluster_fields:
        resolved_cluster_fields = list(_DEFAULT_PREDICTION_EVENT_CLUSTER_FIELDS)

    retention_days = raw_contract.get(
        "retention_days",
        _DEFAULT_PREDICTION_LOG_RETENTION_DAYS,
    )
    try:
        resolved_retention_days = max(int(retention_days), 1)
    except (TypeError, ValueError):
        resolved_retention_days = _DEFAULT_PREDICTION_LOG_RETENTION_DAYS

    return {
        "dataset": dataset,
        "table": table,
        "partition_field": (
            str(raw_contract.get("partition_field", "")).strip()
            or "prediction_timestamp"
        ),
        "partition_granularity": (
            str(raw_contract.get("partition_granularity", "")).strip().upper()
            or _DEFAULT_BIGQUERY_PARTITION_GRANULARITY
        ),
        "cluster_fields": resolved_cluster_fields,
        "retention_days": resolved_retention_days,
    }


def _prediction_event_bigquery_project_id(storage_config: dict[str, Any]) -> str:
    project_id = str(storage_config.get("bigquery_project_id", "")).strip()
    if not project_id:
        raise ValueError("Prediction-event BigQuery storage requires a GCP project ID")
    return project_id


def _prediction_event_bigquery_table_id(storage_config: dict[str, Any]) -> str:
    project_id = _prediction_event_bigquery_project_id(storage_config)
    contract = _prediction_event_bigquery_contract(storage_config)
    return f"{project_id}.{contract['dataset']}.{contract['table']}"


def _prediction_event_bigquery_client(storage_config: dict[str, Any]) -> Any:
    return _bigquery_module().Client(
        project=_prediction_event_bigquery_project_id(storage_config)
    )


def _prediction_event_bigquery_not_found(storage_config: dict[str, Any]) -> bool:
    client = _prediction_event_bigquery_client(storage_config)
    table_id = _prediction_event_bigquery_table_id(storage_config)
    try:
        client.get_table(table_id)
    except _google_exceptions_module().NotFound:
        return True
    return False


def _prediction_event_bigquery_time_partitioning(
    bigquery: Any,
    contract: dict[str, Any],
) -> Any:
    partition_type = contract["partition_granularity"]
    enum = getattr(bigquery, "TimePartitioningType", None)
    if enum is not None:
        partition_type = getattr(enum, partition_type, partition_type)

    time_partitioning = getattr(bigquery, "TimePartitioning", None)
    expiration_ms = contract["retention_days"] * 24 * 60 * 60 * 1000
    if time_partitioning is None:
        return types.SimpleNamespace(
            type_=partition_type,
            field=contract["partition_field"],
            expiration_ms=expiration_ms,
            require_partition_filter=False,
        )

    return time_partitioning(
        type_=partition_type,
        field=contract["partition_field"],
        expiration_ms=expiration_ms,
        require_partition_filter=False,
    )


def _prediction_event_bigquery_schema_update_options(bigquery: Any) -> list[Any]:
    schema_update_option = getattr(bigquery, "SchemaUpdateOption", None)
    allow_field_addition = getattr(
        schema_update_option,
        "ALLOW_FIELD_ADDITION",
        "ALLOW_FIELD_ADDITION",
    )
    return [allow_field_addition]


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

    return _normalized_prediction_frame(frame)


def _prediction_event_bigquery_write_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame

    frame = _normalized_prediction_frame(frame)
    if "requested_spot_ids" in frame.columns:
        frame["requested_spot_ids"] = frame["requested_spot_ids"].apply(json.dumps)
    return frame


def _validate_prediction_event_bigquery_frame(
    frame: pd.DataFrame,
    contract: dict[str, Any],
) -> None:
    partition_field = contract["partition_field"]
    if partition_field not in frame.columns:
        raise ValueError(
            "Prediction-event BigQuery contract requires partition field "
            f"'{partition_field}'"
        )

    missing_cluster_fields = [
        field for field in contract["cluster_fields"] if field not in frame.columns
    ]
    if missing_cluster_fields:
        missing = ", ".join(missing_cluster_fields)
        raise ValueError(
            "Prediction-event BigQuery contract requires cluster fields present in the write frame: "
            f"{missing}"
        )


def _write_prediction_events_bigquery(
    storage_config: dict[str, Any],
    rows: list[dict[str, Any]],
) -> None:
    bigquery = _bigquery_module()
    client = _prediction_event_bigquery_client(storage_config)
    contract = _prediction_event_bigquery_contract(storage_config)
    write_frame = _prediction_event_bigquery_write_frame(rows)
    _validate_prediction_event_bigquery_frame(write_frame, contract)
    table_missing = _prediction_event_bigquery_not_found(storage_config)

    job_config_kwargs: dict[str, Any] = {
        "write_disposition": "WRITE_APPEND",
        "schema_update_options": _prediction_event_bigquery_schema_update_options(
            bigquery
        ),
    }
    if table_missing:
        job_config_kwargs["time_partitioning"] = (
            _prediction_event_bigquery_time_partitioning(bigquery, contract)
        )
        job_config_kwargs["clustering_fields"] = contract["cluster_fields"]

    job_config = bigquery.LoadJobConfig(**job_config_kwargs)
    client.load_table_from_dataframe(
        write_frame,
        _prediction_event_bigquery_table_id(storage_config),
        job_config=job_config,
    ).result()


def _prediction_event_bigquery_query(storage_config: dict[str, Any]) -> str:
    return f"""
    WITH base AS (
        SELECT
            prediction_timestamp,
            forecast_time,
            quality_index,
            endpoint,
            model_version,
            spot_id,
            spot_name,
            requested_spot_ids,
            MAX(prediction_timestamp) OVER () AS latest_prediction_timestamp
        FROM `{_prediction_event_bigquery_table_id(storage_config)}`
    ),
    retained AS (
        SELECT
            prediction_timestamp,
            forecast_time,
            quality_index,
            endpoint,
            model_version,
            spot_id,
            spot_name,
            requested_spot_ids
        FROM base
        WHERE prediction_timestamp >= TIMESTAMP_SUB(
            latest_prediction_timestamp,
            INTERVAL @retention_days DAY
        )
    ),
    ranked AS (
        SELECT
            prediction_timestamp,
            forecast_time,
            quality_index,
            endpoint,
            model_version,
            spot_id,
            spot_name,
            requested_spot_ids,
            ROW_NUMBER() OVER (
                PARTITION BY model_version
                ORDER BY prediction_timestamp DESC, forecast_time DESC
            ) AS retained_row_number
        FROM retained
        WHERE @model_version = '' OR model_version = @model_version
    )
    SELECT
        prediction_timestamp,
        forecast_time,
        quality_index,
        endpoint,
        model_version,
        spot_id,
        spot_name,
        requested_spot_ids
    FROM ranked
    WHERE retained_row_number <= @max_rows
    ORDER BY prediction_timestamp, forecast_time
    """


def _prediction_event_bigquery_query_job_config(
    bigquery: Any,
    *,
    retention_days: int,
    max_rows: int,
    model_version: str | None,
) -> Any:
    return bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("retention_days", "INT64", retention_days),
            bigquery.ScalarQueryParameter("max_rows", "INT64", max_rows),
            bigquery.ScalarQueryParameter(
                "model_version",
                "STRING",
                str(model_version or ""),
            ),
        ]
    )


def _read_prediction_rows_bigquery(
    storage_config: dict[str, Any],
    *,
    max_rows: int | None = None,
    model_version: str | None = None,
    retention_days: int | None = None,
) -> pd.DataFrame:
    if _prediction_event_bigquery_not_found(storage_config):
        return pd.DataFrame()

    bigquery = _bigquery_module()
    client = _prediction_event_bigquery_client(storage_config)
    job_config = _prediction_event_bigquery_query_job_config(
        bigquery,
        retention_days=_prediction_log_retention_days(retention_days),
        max_rows=_prediction_log_max_rows(max_rows),
        model_version=model_version,
    )
    frame = (
        client.query(
            _prediction_event_bigquery_query(storage_config),
            job_config=job_config,
        )
        .result()
        .to_dataframe()
    )
    if frame.empty:
        return frame
    return _normalized_prediction_frame(frame)


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
    storage_config = get_storage_config()
    backend = _prediction_event_storage_backend(storage_config)

    if event_path is not None or backend != "bigquery":
        durable_destination = _prediction_event_write_path(
            event_path,
            working_log_path=destination,
        )

        if durable_destination == destination:
            raise ValueError(
                "Prediction event history path must differ from the retained working log"
            )

        _append_prediction_rows(durable_destination, rows)
    else:
        _write_prediction_events_bigquery(storage_config, rows)

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
    max_rows: int | None = None,
    model_version: str | None = None,
    retention_days: int | None = None,
) -> pd.DataFrame:
    source = prediction_event_log_path(path)
    return _read_prediction_rows(
        source,
        max_rows=max_rows,
        model_version=model_version,
        retention_days=retention_days,
    )


def read_prediction_history(
    event_path: Path | None = None,
    *,
    max_rows: int | None = None,
    model_version: str | None = None,
    retention_days: int | None = None,
) -> pd.DataFrame:
    if event_path is not None:
        source = prediction_event_log_path(event_path)
        return _read_prediction_rows(
            source,
            max_rows=max_rows,
            model_version=model_version,
            retention_days=retention_days,
        )

    storage_config = get_storage_config()
    if _prediction_event_storage_backend(storage_config) == "bigquery":
        return _read_prediction_rows_bigquery(
            storage_config,
            max_rows=max_rows,
            model_version=model_version,
            retention_days=retention_days,
        )

    source = prediction_event_log_path(event_path)
    return _read_prediction_rows(
        source,
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

        storage_config = get_storage_config()
        resolved_event_path = None
        if (
            event_path is not None
            or _prediction_event_storage_backend(storage_config) != "bigquery"
        ):
            resolved_event_path = _prediction_event_write_path(
                event_path,
                working_log_path=log_path,
            )

        predictions_log = read_prediction_history(
            resolved_event_path,
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
