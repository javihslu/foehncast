"""Shared BigQuery SDK utilities.

Lazy-imports the google-cloud-bigquery SDK so modules remain importable
when the SDK is not installed (e.g. local-only or S3-only deployments).
"""

from __future__ import annotations

import importlib
import types
from typing import Any


def bigquery_module() -> Any:
    """Lazy-load the google.cloud.bigquery package."""
    return importlib.import_module("google.cloud.bigquery")


def google_exceptions_module() -> Any:
    """Lazy-load google.api_core.exceptions."""
    return importlib.import_module("google.api_core.exceptions")


def bigquery_time_partitioning(bigquery: Any, contract: dict[str, Any]) -> Any:
    """Build a TimePartitioning object from a warehouse contract dict."""
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


def bigquery_schema_update_options(bigquery: Any) -> list[Any]:
    """Return schema update options allowing field addition."""
    schema_update_option = getattr(bigquery, "SchemaUpdateOption", None)
    allow_field_addition = getattr(
        schema_update_option,
        "ALLOW_FIELD_ADDITION",
        "ALLOW_FIELD_ADDITION",
    )
    return [allow_field_addition]
