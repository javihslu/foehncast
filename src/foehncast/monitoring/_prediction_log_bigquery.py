"""BigQuery storage backend for prediction event persistence.

Handles all BigQuery-specific logic: client creation, DDL (partitioning,
clustering), schema evolution, writes, and retention-aware reads.
"""

from __future__ import annotations

import importlib
import json
import types
from typing import Any

import pandas as pd

from foehncast.monitoring._prediction_log_common import (
    _DEFAULT_BIGQUERY_PARTITION_GRANULARITY,
    _DEFAULT_PREDICTION_EVENT_CLUSTER_FIELDS,
    _DEFAULT_PREDICTION_LOG_RETENTION_DAYS,
    _normalized_prediction_frame,
    _prediction_log_max_rows,
    _prediction_log_retention_days,
)


def _bigquery_module() -> Any:
    return importlib.import_module("google.cloud.bigquery")


def _google_exceptions_module() -> Any:
    return importlib.import_module("google.api_core.exceptions")


def prediction_event_bigquery_contract(
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
    contract = prediction_event_bigquery_contract(storage_config)
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


def write_prediction_events_bigquery(
    storage_config: dict[str, Any],
    rows: list[dict[str, Any]],
) -> None:
    bigquery = _bigquery_module()
    client = _prediction_event_bigquery_client(storage_config)
    contract = prediction_event_bigquery_contract(storage_config)
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


def read_prediction_rows_bigquery(
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
