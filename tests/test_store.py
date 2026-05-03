"""Tests for the feature store interface."""

from __future__ import annotations

import types
from pathlib import Path

import pandas as pd
import pytest

from foehncast.feature_pipeline import store


@pytest.fixture()
def sample_features() -> pd.DataFrame:
    """Small feature dataset for persistence tests."""
    return pd.DataFrame(
        {
            "wind_speed_10m": [10.0, 12.5],
            "wind_gusts_10m": [14.0, 16.5],
            "wind_steadiness": [0.1, 0.2],
        }
    )


def test_write_and_read_features_local(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, sample_features: pd.DataFrame
):
    monkeypatch.setattr(store, "_ROOT", tmp_path)
    monkeypatch.setattr(
        store,
        "get_storage_config",
        lambda: {"backend": "local", "local_path": "data"},
    )

    store.write_features(sample_features, spot_id="silvaplana", dataset="train")

    result = store.read_features(spot_id="silvaplana", dataset="train")
    pd.testing.assert_frame_equal(result, sample_features)


def test_list_datasets_local_returns_sorted_names(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, sample_features: pd.DataFrame
):
    monkeypatch.setattr(store, "_ROOT", tmp_path)
    monkeypatch.setattr(
        store,
        "get_storage_config",
        lambda: {"backend": "local", "local_path": "data"},
    )

    store.write_features(sample_features, spot_id="silvaplana", dataset="validation")
    store.write_features(sample_features, spot_id="urnersee", dataset="train")

    assert store.list_datasets() == ["train", "validation"]


def test_write_features_s3_uses_storage_options(
    monkeypatch: pytest.MonkeyPatch, sample_features: pd.DataFrame
):
    captured: dict[str, object] = {}

    def fake_to_parquet(self: pd.DataFrame, path: str, **kwargs: object) -> None:
        captured["path"] = path
        captured["storage_options"] = kwargs.get("storage_options")

    monkeypatch.setattr(pd.DataFrame, "to_parquet", fake_to_parquet, raising=False)
    monkeypatch.setattr(store, "_ensure_s3_bucket", lambda storage_config: None)
    monkeypatch.setattr(
        store,
        "get_storage_config",
        lambda: {
            "backend": "s3",
            "s3_bucket": "foehncast-data",
            "s3_endpoint": "http://localhost:9000",
        },
    )
    monkeypatch.setenv("OBJECTSTORE_ACCESS_KEY", "minioadmin")
    monkeypatch.setenv("OBJECTSTORE_SECRET_KEY", "minioadmin123")

    store.write_features(sample_features, spot_id="silvaplana", dataset="train")

    assert captured["path"] == "s3://foehncast-data/train/silvaplana.parquet"
    assert captured["storage_options"] == {
        "key": "minioadmin",
        "secret": "minioadmin123",
        "client_kwargs": {"endpoint_url": "http://localhost:9000"},
    }


def test_read_features_s3_uses_storage_options(
    monkeypatch: pytest.MonkeyPatch, sample_features: pd.DataFrame
):
    captured: dict[str, object] = {}

    def fake_read_parquet(path: str, **kwargs: object) -> pd.DataFrame:
        captured["path"] = path
        captured["storage_options"] = kwargs.get("storage_options")
        return sample_features

    monkeypatch.setattr(pd, "read_parquet", fake_read_parquet)
    monkeypatch.setattr(
        store,
        "get_storage_config",
        lambda: {
            "backend": "s3",
            "s3_bucket": "foehncast-data",
            "s3_endpoint": "http://localhost:9000",
        },
    )
    monkeypatch.setenv("OBJECTSTORE_ACCESS_KEY", "minioadmin")
    monkeypatch.setenv("OBJECTSTORE_SECRET_KEY", "minioadmin123")

    result = store.read_features(spot_id="silvaplana", dataset="train")

    pd.testing.assert_frame_equal(result, sample_features)
    assert captured["path"] == "s3://foehncast-data/train/silvaplana.parquet"
    assert captured["storage_options"] == {
        "key": "minioadmin",
        "secret": "minioadmin123",
        "client_kwargs": {"endpoint_url": "http://localhost:9000"},
    }


def test_list_datasets_s3_uses_filesystem(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, object] = {}

    class FakeS3FileSystem:
        def __init__(self, **kwargs: object) -> None:
            captured["init_kwargs"] = kwargs

        def exists(self, path: str) -> bool:
            captured["exists_path"] = path
            return True

        def ls(self, path: str, detail: bool = True) -> list[dict[str, str]]:
            captured["ls_path"] = path
            captured["detail"] = detail
            return [
                {"name": "foehncast-data/train", "type": "directory"},
                {"name": "foehncast-data/validation", "type": "directory"},
                {"name": "foehncast-data/README.txt", "type": "file"},
            ]

    monkeypatch.setattr(
        store,
        "_s3fs_module",
        lambda: types.SimpleNamespace(S3FileSystem=FakeS3FileSystem),
    )
    monkeypatch.setattr(
        store,
        "get_storage_config",
        lambda: {
            "backend": "s3",
            "s3_bucket": "foehncast-data",
            "s3_endpoint": "http://localhost:9000",
        },
    )
    monkeypatch.setenv("OBJECTSTORE_ACCESS_KEY", "minioadmin")
    monkeypatch.setenv("OBJECTSTORE_SECRET_KEY", "minioadmin123")

    assert store.list_datasets() == ["train", "validation"]
    assert captured["exists_path"] == "foehncast-data"
    assert captured["ls_path"] == "foehncast-data"
    assert captured["init_kwargs"] == {
        "key": "minioadmin",
        "secret": "minioadmin123",
        "client_kwargs": {"endpoint_url": "http://localhost:9000"},
    }


def test_write_features_s3_creates_missing_bucket(
    monkeypatch: pytest.MonkeyPatch, sample_features: pd.DataFrame
):
    captured: dict[str, object] = {}

    class FakeS3FileSystem:
        def __init__(self, **kwargs: object) -> None:
            captured["init_kwargs"] = kwargs

        def exists(self, path: str) -> bool:
            captured["exists_path"] = path
            return False

        def mkdir(self, path: str) -> None:
            captured["mkdir_path"] = path

    monkeypatch.setattr(
        store,
        "_s3fs_module",
        lambda: types.SimpleNamespace(S3FileSystem=FakeS3FileSystem),
    )
    monkeypatch.setattr(
        pd.DataFrame, "to_parquet", lambda self, path, **kwargs: None, raising=False
    )
    monkeypatch.setattr(
        store,
        "get_storage_config",
        lambda: {
            "backend": "s3",
            "s3_bucket": "foehncast-data",
            "s3_endpoint": "http://localhost:9000",
        },
    )
    monkeypatch.setenv("OBJECTSTORE_ACCESS_KEY", "minioadmin")
    monkeypatch.setenv("OBJECTSTORE_SECRET_KEY", "minioadmin123")

    store.write_features(sample_features, spot_id="silvaplana", dataset="train")

    assert captured["exists_path"] == "foehncast-data"
    assert captured["mkdir_path"] == "foehncast-data"


def test_unsupported_backend_raises_value_error(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(store, "get_storage_config", lambda: {"backend": "sqlite"})

    with pytest.raises(ValueError, match="Unsupported storage backend"):
        store.list_datasets()
