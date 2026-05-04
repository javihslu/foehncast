"""Tests for the feature store interface."""

from __future__ import annotations

import types
from pathlib import Path

import pandas as pd
import pytest

from foehncast.feature_pipeline import store


@pytest.fixture()
def isolated_store_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "OBJECTSTORE_ACCESS_KEY",
        "OBJECTSTORE_SECRET_KEY",
        "OBJECTSTORE_ENDPOINT",
        "FSSPEC_S3_KEY",
        "FSSPEC_S3_SECRET",
        "FSSPEC_S3_ENDPOINT_URL",
        "GCP_PROJECT_ID",
        "GOOGLE_CLOUD_PROJECT",
        "STORAGE_BIGQUERY_PROJECT_ID",
    ):
        monkeypatch.delenv(name, raising=False)


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
    monkeypatch: pytest.MonkeyPatch,
    isolated_store_env: None,
    tmp_path: Path,
    sample_features: pd.DataFrame,
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
    monkeypatch: pytest.MonkeyPatch,
    isolated_store_env: None,
    tmp_path: Path,
    sample_features: pd.DataFrame,
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
    monkeypatch: pytest.MonkeyPatch,
    isolated_store_env: None,
    sample_features: pd.DataFrame,
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
    monkeypatch.setenv("OBJECTSTORE_ENDPOINT", "http://localhost:9000")

    store.write_features(sample_features, spot_id="silvaplana", dataset="train")

    assert captured["path"] == "s3://foehncast-data/train/silvaplana.parquet"
    assert captured["storage_options"] == {
        "key": "minioadmin",
        "secret": "minioadmin123",
        "client_kwargs": {"endpoint_url": "http://localhost:9000"},
    }


def test_read_features_s3_uses_storage_options(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store_env: None,
    sample_features: pd.DataFrame,
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
    monkeypatch.setenv("OBJECTSTORE_ENDPOINT", "http://localhost:9000")

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
    monkeypatch.setenv("OBJECTSTORE_ENDPOINT", "http://localhost:9000")

    assert store.list_datasets() == ["train", "validation"]
    assert captured["exists_path"] == "foehncast-data"
    assert captured["ls_path"] == "foehncast-data"
    assert captured["init_kwargs"] == {
        "key": "minioadmin",
        "secret": "minioadmin123",
        "client_kwargs": {"endpoint_url": "http://localhost:9000"},
    }


def test_write_features_s3_creates_missing_bucket(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store_env: None,
    sample_features: pd.DataFrame,
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
    monkeypatch.setenv("OBJECTSTORE_ENDPOINT", "http://localhost:9000")

    store.write_features(sample_features, spot_id="silvaplana", dataset="train")

    assert captured["exists_path"] == "foehncast-data"
    assert captured["mkdir_path"] == "foehncast-data"


def test_write_features_bigquery_uses_load_job(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store_env: None,
    sample_features: pd.DataFrame,
):
    captured: dict[str, object] = {}

    class FakeLoadJob:
        def result(self) -> None:
            captured["job_completed"] = True

    class FakeClient:
        def __init__(self, project: str) -> None:
            captured["project"] = project

        def load_table_from_dataframe(
            self, frame: pd.DataFrame, table_id: str, job_config: object
        ) -> FakeLoadJob:
            captured["table_id"] = table_id
            captured["frame"] = frame.copy()
            captured["write_disposition"] = job_config.write_disposition
            return FakeLoadJob()

    class FakeLoadJobConfig:
        def __init__(self, write_disposition: str) -> None:
            self.write_disposition = write_disposition

    monkeypatch.setattr(
        store,
        "_bigquery_module",
        lambda: types.SimpleNamespace(
            Client=FakeClient, LoadJobConfig=FakeLoadJobConfig
        ),
    )
    monkeypatch.setattr(store, "get_gcp_project_id", lambda: "demo-project")
    monkeypatch.setattr(
        store,
        "get_storage_config",
        lambda: {
            "backend": "bigquery",
            "bigquery_dataset": "foehncast",
            "bigquery_table": "forecast_features",
        },
    )

    frame = sample_features.copy()
    frame.index = pd.to_datetime(["2025-01-01T00:00:00", "2025-01-01T01:00:00"])
    frame.index.name = "time"
    frame["spot_name"] = ["Silvaplana", "Silvaplana"]

    store.write_features(frame, spot_id="silvaplana", dataset="train")

    written = captured["frame"]
    assert captured["project"] == "demo-project"
    assert captured["table_id"] == "demo-project.foehncast.forecast_features"
    assert captured["write_disposition"] == "WRITE_APPEND"
    assert captured["job_completed"] is True
    assert list(written["spot_id"]) == ["silvaplana", "silvaplana"]
    assert list(written["dataset_name"]) == ["train", "train"]
    assert "forecast_time" in written.columns


def test_read_features_bigquery_restores_time_index(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store_env: None,
    sample_features: pd.DataFrame,
):
    captured: dict[str, object] = {}

    class FakeRowIterator:
        def to_dataframe(self) -> pd.DataFrame:
            return pd.DataFrame(
                {
                    "forecast_time": pd.to_datetime(
                        ["2025-01-01T00:00:00", "2025-01-01T01:00:00"]
                    ),
                    "spot_id": ["silvaplana", "silvaplana"],
                    "spot_name": ["Silvaplana", "Silvaplana"],
                    "dataset_name": ["train", "train"],
                    "wind_speed_10m": [10.0, 12.5],
                    "wind_gusts_10m": [14.0, 16.5],
                    "wind_steadiness": [0.1, 0.2],
                }
            )

    class FakeQueryJob:
        def result(self) -> FakeRowIterator:
            return FakeRowIterator()

    class FakeClient:
        def __init__(self, project: str) -> None:
            captured["project"] = project

        def get_table(self, table_id: str) -> object:
            captured["table_id"] = table_id
            return object()

        def query(self, query: str, job_config: object | None = None) -> FakeQueryJob:
            captured["query"] = query
            captured["job_config"] = job_config
            return FakeQueryJob()

    class FakeScalarQueryParameter:
        def __init__(self, name: str, param_type: str, value: str) -> None:
            self.name = name
            self.param_type = param_type
            self.value = value

    class FakeQueryJobConfig:
        def __init__(self, query_parameters: list[object]) -> None:
            self.query_parameters = query_parameters

    monkeypatch.setattr(
        store,
        "_bigquery_module",
        lambda: types.SimpleNamespace(
            Client=FakeClient,
            QueryJobConfig=FakeQueryJobConfig,
            ScalarQueryParameter=FakeScalarQueryParameter,
        ),
    )
    monkeypatch.setattr(
        store,
        "_google_exceptions_module",
        lambda: types.SimpleNamespace(NotFound=KeyError),
    )
    monkeypatch.setattr(store, "get_gcp_project_id", lambda: "demo-project")
    monkeypatch.setattr(
        store,
        "get_storage_config",
        lambda: {
            "backend": "bigquery",
            "bigquery_dataset": "foehncast",
            "bigquery_table": "forecast_features",
        },
    )

    result = store.read_features(spot_id="silvaplana", dataset="train")

    assert captured["project"] == "demo-project"
    assert captured["table_id"] == "demo-project.foehncast.forecast_features"
    assert "dataset_name" not in result.columns
    assert result.index.name == "time"
    assert list(result["spot_id"]) == ["silvaplana", "silvaplana"]

    parameters = captured["job_config"].query_parameters
    assert [(param.name, param.value) for param in parameters] == [
        ("spot_id", "silvaplana"),
        ("dataset_name", "train"),
    ]


def test_read_features_bigquery_raises_file_not_found_for_empty_result(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store_env: None,
):
    class FakeRowIterator:
        def to_dataframe(self) -> pd.DataFrame:
            return pd.DataFrame()

    class FakeQueryJob:
        def result(self) -> FakeRowIterator:
            return FakeRowIterator()

    class FakeClient:
        def __init__(self, project: str) -> None:
            self.project = project

        def get_table(self, table_id: str) -> object:
            return object()

        def query(self, query: str, job_config: object | None = None) -> FakeQueryJob:
            return FakeQueryJob()

    monkeypatch.setattr(
        store,
        "_bigquery_module",
        lambda: types.SimpleNamespace(
            Client=FakeClient,
            QueryJobConfig=lambda query_parameters: types.SimpleNamespace(
                query_parameters=query_parameters
            ),
            ScalarQueryParameter=lambda name, param_type, value: types.SimpleNamespace(
                name=name,
                param_type=param_type,
                value=value,
            ),
        ),
    )
    monkeypatch.setattr(
        store,
        "_google_exceptions_module",
        lambda: types.SimpleNamespace(NotFound=KeyError),
    )
    monkeypatch.setattr(store, "get_gcp_project_id", lambda: "demo-project")
    monkeypatch.setattr(
        store,
        "get_storage_config",
        lambda: {
            "backend": "bigquery",
            "bigquery_dataset": "foehncast",
            "bigquery_table": "forecast_features",
        },
    )

    with pytest.raises(FileNotFoundError, match="No BigQuery feature rows found"):
        store.read_features(spot_id="silvaplana", dataset="train")


def test_list_datasets_bigquery_returns_sorted_names(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store_env: None,
):
    captured: dict[str, object] = {}

    class FakeQueryJob:
        def result(self) -> list[dict[str, str]]:
            return [
                {"dataset_name": "train"},
                {"dataset_name": "validation"},
            ]

    class FakeClient:
        def __init__(self, project: str) -> None:
            captured["project"] = project

        def get_table(self, table_id: str) -> object:
            captured["table_id"] = table_id
            return object()

        def query(self, query: str, job_config: object | None = None) -> FakeQueryJob:
            captured["query"] = query
            return FakeQueryJob()

    monkeypatch.setattr(
        store,
        "_bigquery_module",
        lambda: types.SimpleNamespace(Client=FakeClient),
    )
    monkeypatch.setattr(
        store,
        "_google_exceptions_module",
        lambda: types.SimpleNamespace(NotFound=KeyError),
    )
    monkeypatch.setattr(store, "get_gcp_project_id", lambda: "demo-project")
    monkeypatch.setattr(
        store,
        "get_storage_config",
        lambda: {
            "backend": "bigquery",
            "bigquery_dataset": "foehncast",
            "bigquery_table": "forecast_features",
        },
    )

    assert store.list_datasets() == ["train", "validation"]
    assert captured["project"] == "demo-project"
    assert captured["table_id"] == "demo-project.foehncast.forecast_features"


def test_unsupported_backend_raises_value_error(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store_env: None,
):
    monkeypatch.setattr(store, "get_storage_config", lambda: {"backend": "sqlite"})

    with pytest.raises(ValueError, match="Unsupported storage backend"):
        store.list_datasets()
