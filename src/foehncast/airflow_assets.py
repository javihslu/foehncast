"""Stable Airflow asset URI builders for FoehnCast pipeline surfaces."""

from __future__ import annotations

from urllib.parse import quote


def _asset_segment(value: str) -> str:
    cleaned = value.strip().lower()
    return quote(cleaned or "default", safe="")


def curated_feature_store_asset_uri(dataset: str) -> str:
    return f"x-foehncast://feature-pipeline/curated/{_asset_segment(dataset)}"


def feast_feature_store_asset_uri(dataset: str) -> str:
    return f"x-foehncast://feast/feature-store/{_asset_segment(dataset)}"


def training_request_asset_uri(dataset: str, stage: str = "production") -> str:
    return (
        "x-foehncast://airflow/training-request/"
        f"{_asset_segment(dataset)}/{_asset_segment(stage)}"
    )


def mlflow_training_run_asset_uri(dataset: str) -> str:
    return f"x-foehncast://mlflow/training-run/{_asset_segment(dataset)}"


def mlflow_evaluation_asset_uri(dataset: str) -> str:
    return f"x-foehncast://mlflow/evaluation/{_asset_segment(dataset)}"


def mlflow_registry_asset_uri(model_name: str = "foehncast") -> str:
    return f"x-foehncast://mlflow/model-registry/{_asset_segment(model_name)}"