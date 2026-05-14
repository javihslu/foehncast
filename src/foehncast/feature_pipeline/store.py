"""Persist curated features via the supported S3 or BigQuery backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
import importlib
import types
from typing import Any

import pandas as pd

from foehncast.config import get_storage_config
from foehncast.env import env_value

_BQ_TIME_COLUMN = "forecast_time"
_BQ_DATASET_COLUMN = "dataset_name"
_BQ_SPOT_COLUMN = "spot_id"
_DEFAULT_BIGQUERY_PARTITION_GRANULARITY = "DAY"
_DEFAULT_BIGQUERY_RETENTION_DAYS = 730
_DEFAULT_BIGQUERY_CLUSTER_FIELDS = (_BQ_DATASET_COLUMN, _BQ_SPOT_COLUMN)


class FeatureStoreBackend(ABC):
    def __init__(self, storage_config: dict[str, Any]) -> None:
        self.storage_config = storage_config

    @abstractmethod
    def write_features(self, df: pd.DataFrame, spot_id: str, dataset: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def read_features(self, spot_id: str, dataset: str) -> pd.DataFrame:
        raise NotImplementedError

    @abstractmethod
    def list_datasets(self) -> list[str]:
        raise NotImplementedError


class S3FeatureStoreBackend(FeatureStoreBackend):
    def write_features(self, df: pd.DataFrame, spot_id: str, dataset: str) -> None:
        _ensure_s3_bucket(self.storage_config)
        df.to_parquet(
            _s3_feature_path(self.storage_config, spot_id, dataset),
            storage_options=_s3_storage_options(self.storage_config),
        )

    def read_features(self, spot_id: str, dataset: str) -> pd.DataFrame:
        return pd.read_parquet(
            _s3_feature_path(self.storage_config, spot_id, dataset),
            storage_options=_s3_storage_options(self.storage_config),
        )

    def list_datasets(self) -> list[str]:
        filesystem = _s3_filesystem(self.storage_config)
        root = _s3_bucket(self.storage_config)
        if not filesystem.exists(root):
            return []

        datasets = []
        for entry in filesystem.ls(root, detail=True):
            if entry["type"] != "directory":
                continue
            name = entry["name"].removeprefix(f"{root}/")
            if name:
                datasets.append(name)
        return sorted(datasets)


class BigQueryFeatureStoreBackend(FeatureStoreBackend):
    def write_features(self, df: pd.DataFrame, spot_id: str, dataset: str) -> None:
        _write_features_bigquery(
            self.storage_config,
            df=df,
            spot_id=spot_id,
            dataset=dataset,
        )

    def read_features(self, spot_id: str, dataset: str) -> pd.DataFrame:
        return _read_features_bigquery(
            self.storage_config,
            spot_id=spot_id,
            dataset=dataset,
        )

    def list_datasets(self) -> list[str]:
        return _list_datasets_bigquery(self.storage_config)


def _storage_backend(storage_config: dict[str, Any]) -> str:
    backend = storage_config["backend"]
    if backend not in {"s3", "bigquery"}:
        raise ValueError(f"Unsupported storage backend: {backend}")
    return backend


def _s3_bucket(storage_config: dict[str, Any]) -> str:
    bucket_name = storage_config["s3_bucket"].strip("/")
    if not bucket_name:
        raise ValueError("S3 bucket name must not be empty")
    return bucket_name


def _objectstore_credentials() -> tuple[str | None, str | None]:
    access_key = env_value("OBJECTSTORE_ACCESS_KEY", "FSSPEC_S3_KEY")
    secret_key = env_value("OBJECTSTORE_SECRET_KEY", "FSSPEC_S3_SECRET")
    return access_key, secret_key


def _s3_endpoint(storage_config: dict[str, Any]) -> str | None:
    return env_value(
        "OBJECTSTORE_ENDPOINT", "FSSPEC_S3_ENDPOINT_URL"
    ) or storage_config.get("s3_endpoint")


def _s3_storage_options(storage_config: dict[str, Any]) -> dict[str, Any]:
    options: dict[str, Any] = {}
    access_key, secret_key = _objectstore_credentials()
    if access_key:
        options["key"] = access_key
    if secret_key:
        options["secret"] = secret_key

    endpoint = _s3_endpoint(storage_config)
    if endpoint:
        options["client_kwargs"] = {"endpoint_url": endpoint}
    return options


def _s3fs_module() -> Any:
    return importlib.import_module("s3fs")


def _bigquery_module() -> Any:
    return importlib.import_module("google.cloud.bigquery")


def _google_exceptions_module() -> Any:
    return importlib.import_module("google.api_core.exceptions")


def _s3_feature_path(storage_config: dict[str, Any], spot_id: str, dataset: str) -> str:
    return f"s3://{_s3_bucket(storage_config)}/{dataset}/{spot_id}.parquet"


def _s3_filesystem(storage_config: dict[str, Any]) -> Any:
    return _s3fs_module().S3FileSystem(**_s3_storage_options(storage_config))


def _bigquery_project_id(storage_config: dict[str, Any]) -> str:
    project_id = str(storage_config.get("bigquery_project_id", "")).strip()
    if not project_id:
        raise ValueError("BigQuery storage requires a GCP project ID")
    return project_id


def _bigquery_dataset(storage_config: dict[str, Any]) -> str:
    dataset = storage_config.get("bigquery_dataset", "foehncast").strip()
    if not dataset:
        raise ValueError("BigQuery dataset must not be empty")
    return dataset


def _bigquery_table(storage_config: dict[str, Any]) -> str:
    table = storage_config.get("bigquery_table", "forecast_features").strip()
    if not table:
        raise ValueError("BigQuery table must not be empty")
    return table


def _bigquery_table_id(storage_config: dict[str, Any]) -> str:
    project_id = _bigquery_project_id(storage_config)
    dataset = _bigquery_dataset(storage_config)
    table = _bigquery_table(storage_config)
    return f"{project_id}.{dataset}.{table}"


def _bigquery_client(storage_config: dict[str, Any]) -> Any:
    return _bigquery_module().Client(project=_bigquery_project_id(storage_config))


def _bigquery_curated_feature_contract(
    storage_config: dict[str, Any],
) -> dict[str, Any]:
    warehouse_contracts = storage_config.get("warehouse_contracts", {})
    raw_contract = {}
    if isinstance(warehouse_contracts, dict):
        candidate = warehouse_contracts.get("curated_features", {})
        if isinstance(candidate, dict):
            raw_contract = candidate

    cluster_fields = raw_contract.get(
        "cluster_fields",
        _DEFAULT_BIGQUERY_CLUSTER_FIELDS,
    )
    resolved_cluster_fields = [
        str(field).strip() for field in cluster_fields if str(field).strip()
    ]
    if not resolved_cluster_fields:
        resolved_cluster_fields = list(_DEFAULT_BIGQUERY_CLUSTER_FIELDS)

    retention_days = raw_contract.get(
        "retention_days",
        _DEFAULT_BIGQUERY_RETENTION_DAYS,
    )
    try:
        resolved_retention_days = max(int(retention_days), 1)
    except (TypeError, ValueError):
        resolved_retention_days = _DEFAULT_BIGQUERY_RETENTION_DAYS

    return {
        "partition_field": (
            str(raw_contract.get("partition_field", "")).strip() or _BQ_TIME_COLUMN
        ),
        "partition_granularity": (
            str(raw_contract.get("partition_granularity", "")).strip().upper()
            or _DEFAULT_BIGQUERY_PARTITION_GRANULARITY
        ),
        "cluster_fields": resolved_cluster_fields,
        "retention_days": resolved_retention_days,
    }


def _bigquery_time_partitioning(bigquery: Any, contract: dict[str, Any]) -> Any:
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


def _bigquery_schema_update_options(bigquery: Any) -> list[Any]:
    schema_update_option = getattr(bigquery, "SchemaUpdateOption", None)
    allow_field_addition = getattr(
        schema_update_option,
        "ALLOW_FIELD_ADDITION",
        "ALLOW_FIELD_ADDITION",
    )
    return [allow_field_addition]


def _validate_bigquery_contract_frame(
    frame: pd.DataFrame,
    contract: dict[str, Any],
) -> None:
    partition_field = contract["partition_field"]
    if partition_field not in frame.columns:
        raise ValueError(
            f"Curated BigQuery contract requires partition field '{partition_field}'"
        )

    missing_cluster_fields = [
        field for field in contract["cluster_fields"] if field not in frame.columns
    ]
    if missing_cluster_fields:
        missing = ", ".join(missing_cluster_fields)
        raise ValueError(
            "Curated BigQuery contract requires cluster fields present in the write frame: "
            f"{missing}"
        )


def _bigquery_not_found(storage_config: dict[str, Any]) -> bool:
    client = _bigquery_client(storage_config)
    table_id = _bigquery_table_id(storage_config)
    try:
        client.get_table(table_id)
    except _google_exceptions_module().NotFound:
        return True
    return False


def _bigquery_slice_job_config(bigquery: Any, spot_id: str, dataset: str) -> Any:
    return bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("spot_id", "STRING", spot_id),
            bigquery.ScalarQueryParameter("dataset_name", "STRING", dataset),
        ]
    )


def _delete_features_bigquery(
    storage_config: dict[str, Any], spot_id: str, dataset: str
) -> None:
    if _bigquery_not_found(storage_config):
        return

    bigquery = _bigquery_module()
    client = _bigquery_client(storage_config)
    query = f"""
    DELETE FROM `{_bigquery_table_id(storage_config)}`
    WHERE spot_id = @spot_id AND dataset_name = @dataset_name
    """
    client.query(
        query,
        job_config=_bigquery_slice_job_config(bigquery, spot_id, dataset),
    ).result()


def _bigquery_write_frame(df: pd.DataFrame, spot_id: str, dataset: str) -> pd.DataFrame:
    frame = df.copy()

    if isinstance(frame.index, pd.DatetimeIndex):
        index_name = frame.index.name or "index"
        frame = frame.reset_index().rename(columns={index_name: _BQ_TIME_COLUMN})
    elif "time" in frame.columns:
        frame[_BQ_TIME_COLUMN] = pd.to_datetime(frame["time"])
    else:
        raise KeyError(
            "BigQuery feature storage requires a DatetimeIndex or 'time' column"
        )

    frame[_BQ_TIME_COLUMN] = pd.to_datetime(frame[_BQ_TIME_COLUMN])
    frame[_BQ_SPOT_COLUMN] = spot_id
    frame[_BQ_DATASET_COLUMN] = dataset
    return frame


def _write_features_bigquery(
    storage_config: dict[str, Any], df: pd.DataFrame, spot_id: str, dataset: str
) -> None:
    bigquery = _bigquery_module()
    client = _bigquery_client(storage_config)
    write_frame = _bigquery_write_frame(df, spot_id=spot_id, dataset=dataset)
    contract = _bigquery_curated_feature_contract(storage_config)
    _validate_bigquery_contract_frame(write_frame, contract)
    table_missing = _bigquery_not_found(storage_config)
    if not table_missing:
        _delete_features_bigquery(storage_config, spot_id=spot_id, dataset=dataset)

    job_config_kwargs: dict[str, Any] = {
        "write_disposition": "WRITE_APPEND",
        "schema_update_options": _bigquery_schema_update_options(bigquery),
    }
    if table_missing:
        job_config_kwargs["time_partitioning"] = _bigquery_time_partitioning(
            bigquery,
            contract,
        )
        job_config_kwargs["clustering_fields"] = contract["cluster_fields"]

    job_config = bigquery.LoadJobConfig(**job_config_kwargs)
    client.load_table_from_dataframe(
        write_frame,
        _bigquery_table_id(storage_config),
        job_config=job_config,
    ).result()


def _read_features_bigquery(
    storage_config: dict[str, Any], spot_id: str, dataset: str
) -> pd.DataFrame:
    if _bigquery_not_found(storage_config):
        raise FileNotFoundError(
            f"BigQuery table '{_bigquery_table_id(storage_config)}' was not found"
        )

    bigquery = _bigquery_module()
    client = _bigquery_client(storage_config)
    query = f"""
    SELECT *
    FROM `{_bigquery_table_id(storage_config)}`
    WHERE spot_id = @spot_id AND dataset_name = @dataset_name
    ORDER BY forecast_time
    """
    job_config = _bigquery_slice_job_config(bigquery, spot_id, dataset)
    result = client.query(query, job_config=job_config).result().to_dataframe()
    if result.empty:
        raise FileNotFoundError(
            f"No BigQuery feature rows found for spot '{spot_id}' and dataset '{dataset}'"
        )

    result[_BQ_TIME_COLUMN] = pd.to_datetime(result[_BQ_TIME_COLUMN])
    result = result.drop(columns=[_BQ_DATASET_COLUMN, _BQ_SPOT_COLUMN], errors="ignore")
    result = result.rename(columns={_BQ_TIME_COLUMN: "time"}).set_index("time")
    result.index.name = "time"
    return result


def _list_datasets_bigquery(storage_config: dict[str, Any]) -> list[str]:
    if _bigquery_not_found(storage_config):
        return []

    client = _bigquery_client(storage_config)
    query = f"""
    SELECT DISTINCT dataset_name
    FROM `{_bigquery_table_id(storage_config)}`
    ORDER BY dataset_name
    """
    rows = client.query(query).result()
    return [row[_BQ_DATASET_COLUMN] for row in rows]


def _ensure_s3_bucket(storage_config: dict[str, Any]) -> None:
    filesystem = _s3_filesystem(storage_config)
    bucket = _s3_bucket(storage_config)
    if filesystem.exists(bucket):
        return
    filesystem.mkdir(bucket)


def _feature_store(storage_config: dict[str, Any]) -> FeatureStoreBackend:
    backend = _storage_backend(storage_config)

    if backend == "bigquery":
        return BigQueryFeatureStoreBackend(storage_config)

    return S3FeatureStoreBackend(storage_config)


def write_features(df: pd.DataFrame, spot_id: str, dataset: str) -> None:
    """Persist feature rows for one spot and dataset."""
    _feature_store(get_storage_config()).write_features(
        df, spot_id=spot_id, dataset=dataset
    )


def read_features(spot_id: str, dataset: str) -> pd.DataFrame:
    """Load feature rows for one spot and dataset."""
    return _feature_store(get_storage_config()).read_features(
        spot_id=spot_id, dataset=dataset
    )


def list_datasets() -> list[str]:
    """List available datasets in the configured feature store."""
    return _feature_store(get_storage_config()).list_datasets()
