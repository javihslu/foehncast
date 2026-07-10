"""BigQuery storage backend for prediction event persistence.

Handles all BigQuery-specific logic: client creation, DDL (partitioning,
clustering), schema evolution, writes, and retention-aware reads.
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

from foehncast._bigquery import (
    bigquery_module as _bigquery_module,
    bigquery_schema_update_options as _bigquery_schema_update_options,
    bigquery_time_partitioning as _bigquery_time_partitioning,
    google_exceptions_module as _google_exceptions_module,
)
from foehncast.monitoring._prediction_log_common import (
    _normalized_prediction_frame,
    _prediction_log_max_rows,
    _prediction_log_retention_days,
)


def _prediction_event_bigquery_project_id(storage_config: dict[str, Any]) -> str:
    project_id = str(storage_config.get("bigquery_project_id", "")).strip()
    if not project_id:
        raise ValueError("Prediction-event BigQuery storage requires a GCP project ID")
    return project_id


def _prediction_event_bigquery_table_id(storage_config: dict[str, Any]) -> str:
    project_id = _prediction_event_bigquery_project_id(storage_config)
    contract = storage_config["warehouse_contracts"]["prediction_events"]
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
    contract = storage_config["warehouse_contracts"]["prediction_events"]
    write_frame = _prediction_event_bigquery_write_frame(rows)
    _validate_prediction_event_bigquery_frame(write_frame, contract)
    table_missing = _prediction_event_bigquery_not_found(storage_config)

    job_config_kwargs: dict[str, Any] = {
        "write_disposition": "WRITE_APPEND",
        "schema_update_options": _bigquery_schema_update_options(bigquery),
    }
    if table_missing:
        job_config_kwargs["time_partitioning"] = _bigquery_time_partitioning(
            bigquery, contract
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
