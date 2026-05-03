"""Write features to a config-driven Parquet feature store."""

from __future__ import annotations

import importlib
import os
from pathlib import Path
from typing import Any

import pandas as pd

from foehncast.config import get_storage_config

_ROOT = Path(__file__).resolve().parent.parent.parent


def _storage_backend(storage_config: dict[str, Any]) -> str:
    backend = storage_config["backend"]
    if backend not in {"local", "s3"}:
        raise ValueError(f"Unsupported storage backend: {backend}")
    return backend


def _s3_bucket(storage_config: dict[str, Any]) -> str:
    bucket_name = storage_config["s3_bucket"].strip("/")
    if not bucket_name:
        raise ValueError("S3 bucket name must not be empty")
    return bucket_name


def _objectstore_credentials() -> tuple[str | None, str | None]:
    access_key = os.getenv("OBJECTSTORE_ACCESS_KEY") or os.getenv("FSSPEC_S3_KEY")
    secret_key = os.getenv("OBJECTSTORE_SECRET_KEY") or os.getenv("FSSPEC_S3_SECRET")
    return access_key, secret_key


def _s3_endpoint(storage_config: dict[str, Any]) -> str | None:
    return (
        os.getenv("OBJECTSTORE_ENDPOINT")
        or os.getenv("FSSPEC_S3_ENDPOINT_URL")
        or storage_config.get("s3_endpoint")
    )


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


def _local_feature_path(
    storage_config: dict[str, Any], spot_id: str, dataset: str
) -> Path:
    return _ROOT / storage_config["local_path"] / dataset / f"{spot_id}.parquet"


def _s3_feature_path(storage_config: dict[str, Any], spot_id: str, dataset: str) -> str:
    return f"s3://{_s3_bucket(storage_config)}/{dataset}/{spot_id}.parquet"


def _s3_filesystem(storage_config: dict[str, Any]) -> Any:
    return _s3fs_module().S3FileSystem(**_s3_storage_options(storage_config))


def _ensure_s3_bucket(storage_config: dict[str, Any]) -> None:
    filesystem = _s3_filesystem(storage_config)
    bucket = _s3_bucket(storage_config)
    if filesystem.exists(bucket):
        return
    filesystem.mkdir(bucket)


def write_features(df: pd.DataFrame, spot_id: str, dataset: str) -> None:
    """Persist feature rows for one spot and dataset."""
    storage_config = get_storage_config()
    backend = _storage_backend(storage_config)

    if backend == "local":
        path = _local_feature_path(storage_config, spot_id, dataset)
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(path)
        return

    _ensure_s3_bucket(storage_config)
    df.to_parquet(
        _s3_feature_path(storage_config, spot_id, dataset),
        storage_options=_s3_storage_options(storage_config),
    )


def read_features(spot_id: str, dataset: str) -> pd.DataFrame:
    """Load feature rows for one spot and dataset."""
    storage_config = get_storage_config()
    backend = _storage_backend(storage_config)

    if backend == "local":
        return pd.read_parquet(_local_feature_path(storage_config, spot_id, dataset))

    return pd.read_parquet(
        _s3_feature_path(storage_config, spot_id, dataset),
        storage_options=_s3_storage_options(storage_config),
    )


def list_datasets() -> list[str]:
    """List available datasets in the configured feature store."""
    storage_config = get_storage_config()
    backend = _storage_backend(storage_config)

    if backend == "local":
        root = _ROOT / storage_config["local_path"]
        if not root.exists():
            return []
        return sorted(path.name for path in root.iterdir() if path.is_dir())

    filesystem = _s3_filesystem(storage_config)
    root = _s3_bucket(storage_config)
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
