"""Tests for the feature store interface."""

from __future__ import annotations

import types

import pandas as pd
import pytest

from foehncast.feature_pipeline import store


@pytest.fixture()
def isolated_store_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "STORAGE_S3_ENDPOINT",
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


class _FakeLoadJobConfig:
    def __init__(self, write_disposition: str, **kwargs: object) -> None:
        self.write_disposition = write_disposition
        for name, value in kwargs.items():
            setattr(self, name, value)


class _FakeTimePartitioning:
    def __init__(
        self,
        *,
        type_: object,
        field: str,
        expiration_ms: int,
        require_partition_filter: bool,
    ) -> None:
        self.type_ = type_
        self.field = field
        self.expiration_ms = expiration_ms
        self.require_partition_filter = require_partition_filter


class _FakeScalarQueryParameter:
    def __init__(self, name: str, param_type: str, value: str) -> None:
        self.name = name
        self.param_type = param_type
        self.value = value


class _FakeQueryJobConfig:
    def __init__(self, query_parameters: list[object]) -> None:
        self.query_parameters = query_parameters


class _CompletedJob:
    def result(self) -> None:
        return None


class _FlaggingCompletedJob:
    def __init__(self, captured: dict[str, object], key: str) -> None:
        self._captured = captured
        self._key = key

    def result(self) -> None:
        self._captured[self._key] = True


class _FrameRowIterator:
    def __init__(self, frame: pd.DataFrame | None = None) -> None:
        self.frame = pd.DataFrame() if frame is None else frame

    def to_dataframe(self) -> pd.DataFrame:
        return self.frame.copy()


class _FrameQueryJob:
    def __init__(self, frame: pd.DataFrame | None = None) -> None:
        self.frame = frame

    def result(self) -> _FrameRowIterator:
        return _FrameRowIterator(self.frame)


def _patch_bigquery_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        store,
        "_google_exceptions_module",
        lambda: types.SimpleNamespace(NotFound=KeyError),
    )


def _patch_default_bigquery_storage_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        store,
        "get_storage_config",
        lambda: {
            "backend": "bigquery",
            "bigquery_project_id": "demo-project",
            "bigquery_dataset": "foehncast",
            "bigquery_table": "forecast_features",
        },
    )


def test_write_features_unsupported_backend_raises_value_error(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store_env: None,
    sample_features: pd.DataFrame,
):
    monkeypatch.setattr(store, "get_storage_config", lambda: {"backend": "sqlite"})

    with pytest.raises(ValueError, match="Unsupported storage backend"):
        store.write_features(sample_features, spot_id="silvaplana", dataset="train")


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
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "minioadmin")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "minioadmin123")
    monkeypatch.setenv("STORAGE_S3_ENDPOINT", "http://stale-override:9000")

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
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "minioadmin")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "minioadmin123")

    result = store.read_features(spot_id="silvaplana", dataset="train")

    pd.testing.assert_frame_equal(result, sample_features)
    assert captured["path"] == "s3://foehncast-data/train/silvaplana.parquet"
    assert captured["storage_options"] == {
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
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "minioadmin")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "minioadmin123")

    store.write_features(sample_features, spot_id="silvaplana", dataset="train")

    assert captured["exists_path"] == "foehncast-data"
    assert captured["mkdir_path"] == "foehncast-data"


def test_write_features_bigquery_uses_load_job(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store_env: None,
    sample_features: pd.DataFrame,
):
    captured: dict[str, object] = {}

    class FakeClient:
        def __init__(self, project: str) -> None:
            captured["project"] = project

        def get_table(self, table_id: str) -> object:
            captured["existing_table_id"] = table_id
            return object()

        def load_table_from_dataframe(
            self, frame: pd.DataFrame, table_id: str, job_config: object
        ) -> _FlaggingCompletedJob:
            captured["table_id"] = table_id
            captured["frame"] = frame.copy()
            captured["write_disposition"] = job_config.write_disposition
            captured["time_partitioning"] = getattr(
                job_config, "time_partitioning", None
            )
            captured["clustering_fields"] = getattr(
                job_config, "clustering_fields", None
            )
            captured["schema_update_options"] = job_config.schema_update_options
            return _FlaggingCompletedJob(captured, "job_completed")

        def query(
            self, query: str, job_config: object | None = None
        ) -> _FlaggingCompletedJob:
            captured["delete_query"] = query
            captured["delete_job_config"] = job_config
            return _FlaggingCompletedJob(captured, "delete_completed")

    monkeypatch.setattr(
        store,
        "_bigquery_module",
        lambda: types.SimpleNamespace(
            Client=FakeClient,
            LoadJobConfig=_FakeLoadJobConfig,
            QueryJobConfig=_FakeQueryJobConfig,
            ScalarQueryParameter=_FakeScalarQueryParameter,
            SchemaUpdateOption=types.SimpleNamespace(
                ALLOW_FIELD_ADDITION="ALLOW_FIELD_ADDITION"
            ),
            TimePartitioning=_FakeTimePartitioning,
            TimePartitioningType=types.SimpleNamespace(DAY="DAY"),
        ),
    )
    _patch_bigquery_not_found(monkeypatch)
    _patch_default_bigquery_storage_config(monkeypatch)

    frame = sample_features.copy()
    frame.index = pd.to_datetime(["2025-01-01T00:00:00", "2025-01-01T01:00:00"])
    frame.index.name = "time"
    frame["spot_name"] = ["Silvaplana", "Silvaplana"]

    store.write_features(frame, spot_id="silvaplana", dataset="train")

    written = captured["frame"]
    assert captured["project"] == "demo-project"
    assert captured["table_id"] == "demo-project.foehncast.forecast_features"
    assert captured["write_disposition"] == "WRITE_APPEND"
    assert captured["time_partitioning"] is None
    assert captured["clustering_fields"] is None
    assert captured["schema_update_options"] == ["ALLOW_FIELD_ADDITION"]
    assert captured["delete_completed"] is True
    assert captured["job_completed"] is True
    assert (
        "DELETE FROM `demo-project.foehncast.forecast_features`"
        in captured["delete_query"]
    )
    delete_parameters = captured["delete_job_config"].query_parameters
    assert [(param.name, param.value) for param in delete_parameters] == [
        ("spot_id", "silvaplana"),
        ("dataset_name", "train"),
    ]
    assert list(written["spot_id"]) == ["silvaplana", "silvaplana"]
    assert list(written["dataset_name"]) == ["train", "train"]
    assert "forecast_time" in written.columns


def test_write_features_bigquery_applies_contract_when_table_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store_env: None,
    sample_features: pd.DataFrame,
):
    captured: dict[str, object] = {}

    class FakeClient:
        def __init__(self, project: str) -> None:
            captured["project"] = project

        def get_table(self, table_id: str) -> object:
            captured["missing_table_id"] = table_id
            raise KeyError(table_id)

        def load_table_from_dataframe(
            self, frame: pd.DataFrame, table_id: str, job_config: object
        ) -> _FlaggingCompletedJob:
            captured["table_id"] = table_id
            captured["frame"] = frame.copy()
            captured["write_disposition"] = job_config.write_disposition
            captured["time_partitioning"] = job_config.time_partitioning
            captured["clustering_fields"] = job_config.clustering_fields
            captured["schema_update_options"] = job_config.schema_update_options
            return _FlaggingCompletedJob(captured, "job_completed")

        def query(self, query: str, job_config: object | None = None) -> object:
            captured["unexpected_delete_query"] = query
            raise AssertionError(
                "delete should not run when the BigQuery table is absent"
            )

    monkeypatch.setattr(
        store,
        "_bigquery_module",
        lambda: types.SimpleNamespace(
            Client=FakeClient,
            LoadJobConfig=_FakeLoadJobConfig,
            SchemaUpdateOption=types.SimpleNamespace(
                ALLOW_FIELD_ADDITION="ALLOW_FIELD_ADDITION"
            ),
            TimePartitioning=_FakeTimePartitioning,
            TimePartitioningType=types.SimpleNamespace(DAY="DAY"),
        ),
    )
    _patch_bigquery_not_found(monkeypatch)
    _patch_default_bigquery_storage_config(monkeypatch)

    frame = sample_features.copy()
    frame.index = pd.to_datetime(["2025-01-01T00:00:00", "2025-01-01T01:00:00"])
    frame.index.name = "time"
    frame["spot_name"] = ["Silvaplana", "Silvaplana"]

    store.write_features(frame, spot_id="silvaplana", dataset="train")

    assert captured["project"] == "demo-project"
    assert captured["missing_table_id"] == "demo-project.foehncast.forecast_features"
    assert captured["table_id"] == "demo-project.foehncast.forecast_features"
    assert captured["write_disposition"] == "WRITE_APPEND"
    assert captured["time_partitioning"].field == "forecast_time"
    assert captured["time_partitioning"].type_ == "DAY"
    assert captured["time_partitioning"].expiration_ms == 63072000000
    assert captured["time_partitioning"].require_partition_filter is False
    assert captured["clustering_fields"] == ["dataset_name", "spot_id"]
    assert captured["schema_update_options"] == ["ALLOW_FIELD_ADDITION"]
    assert captured["job_completed"] is True


def test_read_features_bigquery_restores_time_index(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store_env: None,
    sample_features: pd.DataFrame,
):
    captured: dict[str, object] = {}

    restored_frame = pd.DataFrame(
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

    class FakeClient:
        def __init__(self, project: str) -> None:
            captured["project"] = project

        def get_table(self, table_id: str) -> object:
            captured["table_id"] = table_id
            return object()

        def query(self, query: str, job_config: object | None = None) -> _FrameQueryJob:
            captured["query"] = query
            captured["job_config"] = job_config
            return _FrameQueryJob(restored_frame)

    monkeypatch.setattr(
        store,
        "_bigquery_module",
        lambda: types.SimpleNamespace(
            Client=FakeClient,
            QueryJobConfig=_FakeQueryJobConfig,
            ScalarQueryParameter=_FakeScalarQueryParameter,
        ),
    )
    _patch_bigquery_not_found(monkeypatch)
    _patch_default_bigquery_storage_config(monkeypatch)

    result = store.read_features(spot_id="silvaplana", dataset="train")

    assert captured["project"] == "demo-project"
    assert captured["table_id"] == "demo-project.foehncast.forecast_features"
    assert "dataset_name" not in result.columns
    assert "spot_id" not in result.columns
    assert result.index.name == "time"
    assert list(result["wind_speed_10m"]) == [10.0, 12.5]

    parameters = captured["job_config"].query_parameters
    assert [(param.name, param.value) for param in parameters] == [
        ("spot_id", "silvaplana"),
        ("dataset_name", "train"),
    ]


def test_bigquery_round_trip_restores_original_feature_schema(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store_env: None,
):
    written: dict[str, pd.DataFrame] = {}

    class FakeClient:
        def __init__(self, project: str) -> None:
            self.project = project

        def get_table(self, table_id: str) -> object:
            if "frame" not in written:
                raise KeyError(table_id)
            return object()

        def load_table_from_dataframe(
            self, frame: pd.DataFrame, table_id: str, job_config: object
        ) -> _CompletedJob:
            written["frame"] = frame.copy()
            return _CompletedJob()

        def query(
            self, query: str, job_config: object | None = None
        ) -> _CompletedJob | _FrameQueryJob:
            if "DELETE FROM" in query:
                written["frame"] = written["frame"].iloc[0:0].copy()
                return _CompletedJob()
            return _FrameQueryJob(written["frame"])

    monkeypatch.setattr(
        store,
        "_bigquery_module",
        lambda: types.SimpleNamespace(
            Client=FakeClient,
            LoadJobConfig=_FakeLoadJobConfig,
            QueryJobConfig=_FakeQueryJobConfig,
            ScalarQueryParameter=_FakeScalarQueryParameter,
        ),
    )
    _patch_bigquery_not_found(monkeypatch)
    _patch_default_bigquery_storage_config(monkeypatch)

    original = pd.DataFrame(
        {
            "wind_speed_10m": [10.0, 12.5],
            "wind_gusts_10m": [14.0, 16.5],
            "wind_steadiness": [0.1, 0.2],
        },
        index=pd.to_datetime(["2025-01-01T00:00:00", "2025-01-01T01:00:00"]),
    )
    original.index.name = "time"

    store.write_features(original, spot_id="silvaplana", dataset="train")
    restored = store.read_features(spot_id="silvaplana", dataset="train")

    pd.testing.assert_frame_equal(restored, original)


def test_write_features_bigquery_replaces_existing_slice_on_repeated_writes(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store_env: None,
):
    state: dict[str, object] = {"table": None, "delete_calls": 0}

    class FakeClient:
        def __init__(self, project: str) -> None:
            self.project = project

        def get_table(self, table_id: str) -> object:
            if state["table"] is None:
                raise KeyError(table_id)
            return object()

        def load_table_from_dataframe(
            self, frame: pd.DataFrame, table_id: str, job_config: object
        ) -> _CompletedJob:
            existing = state["table"]
            if existing is None:
                state["table"] = frame.copy()
            else:
                state["table"] = pd.concat([existing, frame.copy()], ignore_index=True)
            return _CompletedJob()

        def query(self, query: str, job_config: object | None = None) -> object:
            parameters = {
                param.name: param.value
                for param in getattr(job_config, "query_parameters", [])
            }
            table = state["table"]

            if "DELETE FROM" in query:
                state["delete_calls"] = int(state["delete_calls"]) + 1
                if table is not None:
                    filtered = table.loc[
                        ~(
                            (table["spot_id"] == parameters["spot_id"])
                            & (table["dataset_name"] == parameters["dataset_name"])
                        )
                    ].reset_index(drop=True)
                    state["table"] = filtered
                return _CompletedJob()

            if table is None:
                return _FrameQueryJob()

            filtered = (
                table.loc[
                    (table["spot_id"] == parameters["spot_id"])
                    & (table["dataset_name"] == parameters["dataset_name"])
                ]
                .sort_values("forecast_time")
                .reset_index(drop=True)
            )
            return _FrameQueryJob(filtered)

    monkeypatch.setattr(
        store,
        "_bigquery_module",
        lambda: types.SimpleNamespace(
            Client=FakeClient,
            LoadJobConfig=_FakeLoadJobConfig,
            QueryJobConfig=_FakeQueryJobConfig,
            ScalarQueryParameter=_FakeScalarQueryParameter,
        ),
    )
    _patch_bigquery_not_found(monkeypatch)
    _patch_default_bigquery_storage_config(monkeypatch)

    first = pd.DataFrame(
        {"wind_speed_10m": [10.0, 12.5], "wind_steadiness": [0.1, 0.2]},
        index=pd.to_datetime(["2025-01-01T00:00:00", "2025-01-01T01:00:00"]),
    )
    first.index.name = "time"
    second = pd.DataFrame(
        {"wind_speed_10m": [20.0, 21.5], "wind_steadiness": [0.3, 0.4]},
        index=pd.to_datetime(["2025-01-01T00:00:00", "2025-01-01T01:00:00"]),
    )
    second.index.name = "time"

    store.write_features(first, spot_id="silvaplana", dataset="train")
    store.write_features(second, spot_id="silvaplana", dataset="train")
    restored = store.read_features(spot_id="silvaplana", dataset="train")

    assert state["delete_calls"] == 1
    pd.testing.assert_frame_equal(restored, second)


def test_read_features_bigquery_raises_file_not_found_for_empty_result(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store_env: None,
):
    class FakeClient:
        def __init__(self, project: str) -> None:
            self.project = project

        def get_table(self, table_id: str) -> object:
            return object()

        def query(self, query: str, job_config: object | None = None) -> _FrameQueryJob:
            return _FrameQueryJob()

    monkeypatch.setattr(
        store,
        "_bigquery_module",
        lambda: types.SimpleNamespace(
            Client=FakeClient,
            QueryJobConfig=_FakeQueryJobConfig,
            ScalarQueryParameter=_FakeScalarQueryParameter,
        ),
    )
    _patch_bigquery_not_found(monkeypatch)
    _patch_default_bigquery_storage_config(monkeypatch)

    with pytest.raises(FileNotFoundError, match="No BigQuery feature rows found"):
        store.read_features(spot_id="silvaplana", dataset="train")
