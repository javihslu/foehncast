"""Tests for prediction log persistence and drift monitoring."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import types
from types import SimpleNamespace

import pandas as pd
import pytest

from foehncast.monitoring import prediction_log
from foehncast.monitoring import _prediction_log_bigquery as _bq_mod
from foehncast.monitoring import _prediction_log_common as _common_mod
from tests.bigquery_fakes import (
    FakeCompletedJob,
    FakeLoadJobConfig,
    FakeQueryJobConfig,
    FakeScalarQueryParameter,
    FakeTimePartitioning,
)


class _PredictionFrameRowIterator:
    def __init__(self, frame: pd.DataFrame | None = None) -> None:
        self.frame = pd.DataFrame() if frame is None else frame

    def to_dataframe(self) -> pd.DataFrame:
        return self.frame.copy()


class _PredictionFrameQueryJob:
    def __init__(self, frame: pd.DataFrame | None = None) -> None:
        self.frame = frame

    def result(self) -> _PredictionFrameRowIterator:
        return _PredictionFrameRowIterator(self.frame)


def _patch_prediction_event_bigquery_storage_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        prediction_log,
        "get_storage_config",
        lambda: {
            "backend": "bigquery",
            "bigquery_project_id": "demo-project",
            "warehouse_contracts": {
                "prediction_events": {
                    "dataset": "foehncast_monitoring",
                    "table": "prediction_events",
                    "partition_field": "prediction_timestamp",
                    "partition_granularity": "DAY",
                    "cluster_fields": ["model_version", "endpoint", "spot_id"],
                    "retention_days": 180,
                }
            },
        },
    )


def _patch_prediction_event_bigquery_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        _bq_mod,
        "_google_exceptions_module",
        lambda: types.SimpleNamespace(NotFound=KeyError),
    )


def test_append_prediction_log_and_read_prediction_log_round_trip(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "prediction-log.jsonl"
    payload = {
        "model_version": "7",
        "predictions": [
            {
                "spot_id": "silvaplana",
                "spot_name": "Silvaplana",
                "forecast": [
                    {"time": "2025-01-01T00:00:00+00:00", "quality_index": 2.4},
                    {"time": "2025-01-01T01:00:00+00:00", "quality_index": 2.8},
                ],
            }
        ],
    }

    written = prediction_log.append_prediction_log(
        payload,
        endpoint="predict",
        spot_ids=["silvaplana"],
        path=log_path,
        logged_at=datetime(2026, 5, 11, 10, 0, tzinfo=UTC),
    )

    frame = prediction_log.read_prediction_log(log_path)

    assert written == log_path
    assert len(frame) == 2
    assert list(frame["spot_id"]) == ["silvaplana", "silvaplana"]
    assert list(frame["quality_index"]) == [2.4, 2.8]
    assert list(frame["endpoint"]) == ["predict", "predict"]
    assert list(frame["model_version"]) == ["7", "7"]
    assert (
        frame["prediction_timestamp"].iloc[0].isoformat() == "2026-05-11T10:00:00+00:00"
    )


def test_append_prediction_log_writes_durable_event_history_by_default(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "prediction-log.jsonl"
    event_path = tmp_path / "prediction-events.jsonl"

    prediction_log.append_prediction_log(
        {
            "model_version": "7",
            "predictions": [
                {
                    "spot_id": "silvaplana",
                    "spot_name": "Silvaplana",
                    "forecast": [
                        {"time": "2025-01-01T00:00:00+00:00", "quality_index": 2.4},
                        {"time": "2025-01-01T01:00:00+00:00", "quality_index": 2.8},
                    ],
                }
            ],
        },
        endpoint="predict",
        path=log_path,
        logged_at=datetime(2026, 5, 11, 10, 0, tzinfo=UTC),
    )

    frame = prediction_log.read_prediction_event_log(event_path)

    assert event_path.exists()
    assert len(frame) == 2
    assert list(frame["quality_index"]) == [2.4, 2.8]


def test_prediction_event_log_path_prefers_env_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    event_path = tmp_path / "shared" / "prediction-events.jsonl"
    monkeypatch.setenv("FOEHNCAST_PREDICTION_EVENT_LOG_PATH", str(event_path))

    assert prediction_log.prediction_event_log_path() == event_path


def test_read_prediction_history_prefers_durable_event_store_when_available(
    tmp_path: Path,
) -> None:
    shared_event_path = tmp_path / "shared" / "prediction-events.jsonl"
    local_log_path = tmp_path / "instance-a" / "prediction-log.jsonl"
    remote_log_path = tmp_path / "instance-b" / "prediction-log.jsonl"

    prediction_log.append_prediction_log(
        {
            "model_version": "7",
            "predictions": [
                {
                    "spot_id": "silvaplana",
                    "spot_name": "Silvaplana",
                    "forecast": [
                        {"time": "2025-01-01T00:00:00+00:00", "quality_index": 2.1}
                    ],
                }
            ],
        },
        endpoint="predict",
        path=remote_log_path,
        event_path=shared_event_path,
        logged_at=datetime(2026, 5, 11, 9, 0, tzinfo=UTC),
    )
    prediction_log.append_prediction_log(
        {
            "model_version": "7",
            "predictions": [
                {
                    "spot_id": "silvaplana",
                    "spot_name": "Silvaplana",
                    "forecast": [
                        {"time": "2025-01-01T01:00:00+00:00", "quality_index": 2.3}
                    ],
                }
            ],
        },
        endpoint="predict",
        path=local_log_path,
        event_path=shared_event_path,
        logged_at=datetime(2026, 5, 11, 10, 0, tzinfo=UTC),
    )

    local_frame = prediction_log.read_prediction_log(local_log_path, max_rows=10)
    history_frame = prediction_log.read_prediction_history(
        event_path=shared_event_path,
        max_rows=10,
    )

    assert len(local_frame) == 1
    assert list(local_frame["quality_index"]) == [2.3]
    assert len(history_frame) == 2
    assert list(history_frame["quality_index"]) == [2.1, 2.3]


def test_read_prediction_history_returns_empty_when_durable_store_missing(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "prediction-log.jsonl"
    event_path = tmp_path / "shared" / "prediction-events.jsonl"

    prediction_log.append_prediction_log(
        {
            "model_version": "7",
            "predictions": [
                {
                    "spot_id": "silvaplana",
                    "spot_name": "Silvaplana",
                    "forecast": [
                        {"time": "2025-01-01T00:00:00+00:00", "quality_index": 2.4},
                        {"time": "2025-01-01T01:00:00+00:00", "quality_index": 2.8},
                    ],
                }
            ],
        },
        endpoint="predict",
        path=log_path,
        event_path=log_path.with_name("other-events.jsonl"),
        logged_at=datetime(2026, 5, 11, 10, 0, tzinfo=UTC),
    )

    history_frame = prediction_log.read_prediction_history(
        event_path=event_path,
        max_rows=10,
    )

    assert history_frame.empty


def test_append_prediction_log_rejects_event_path_matching_working_log(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "prediction-log.jsonl"

    with pytest.raises(
        ValueError,
        match="Prediction event history path must differ from the retained working log",
    ):
        prediction_log.append_prediction_log(
            {
                "model_version": "7",
                "predictions": [
                    {
                        "spot_id": "silvaplana",
                        "spot_name": "Silvaplana",
                        "forecast": [
                            {
                                "time": "2025-01-01T00:00:00+00:00",
                                "quality_index": 2.4,
                            }
                        ],
                    }
                ],
            },
            endpoint="predict",
            path=log_path,
            event_path=log_path,
            logged_at=datetime(2026, 5, 11, 10, 0, tzinfo=UTC),
        )


def test_append_prediction_log_trims_to_recent_rows(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "prediction-log.jsonl"

    prediction_log.append_prediction_log(
        {
            "model_version": "7",
            "predictions": [
                {
                    "spot_id": "silvaplana",
                    "spot_name": "Silvaplana",
                    "forecast": [
                        {"time": "2025-01-01T00:00:00+00:00", "quality_index": 2.1},
                        {"time": "2025-01-01T01:00:00+00:00", "quality_index": 2.2},
                    ],
                }
            ],
        },
        endpoint="predict",
        path=log_path,
        max_rows=3,
        logged_at=datetime(2026, 5, 11, 10, 0, tzinfo=UTC),
    )
    prediction_log.append_prediction_log(
        {
            "model_version": "7",
            "predictions": [
                {
                    "spot_id": "silvaplana",
                    "spot_name": "Silvaplana",
                    "forecast": [
                        {"time": "2025-01-01T02:00:00+00:00", "quality_index": 2.3},
                        {"time": "2025-01-01T03:00:00+00:00", "quality_index": 2.4},
                    ],
                }
            ],
        },
        endpoint="predict",
        path=log_path,
        max_rows=3,
        logged_at=datetime(2026, 5, 11, 11, 0, tzinfo=UTC),
    )

    frame = prediction_log.read_prediction_log(log_path, max_rows=3)

    assert len(frame) == 3
    assert list(frame["quality_index"]) == [2.2, 2.3, 2.4]
    assert [value.isoformat() for value in frame["forecast_time"]] == [
        "2025-01-01T01:00:00+00:00",
        "2025-01-01T02:00:00+00:00",
        "2025-01-01T03:00:00+00:00",
    ]


def test_append_prediction_log_preserves_recent_rows_per_model_version(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "prediction-log.jsonl"

    def append(model_version: str, quality_index: float, hour: int) -> None:
        prediction_log.append_prediction_log(
            {
                "model_version": model_version,
                "predictions": [
                    {
                        "spot_id": "silvaplana",
                        "spot_name": "Silvaplana",
                        "forecast": [
                            {
                                "time": f"2025-01-01T{hour:02d}:00:00+00:00",
                                "quality_index": quality_index,
                            }
                        ],
                    }
                ],
            },
            endpoint="predict",
            path=log_path,
            max_rows=2,
            logged_at=datetime(2026, 5, 11, 10, hour, tzinfo=UTC),
        )

    append("7", 2.1, 0)
    append("8", 3.1, 1)
    append("7", 2.2, 2)
    append("8", 3.2, 3)
    append("7", 2.3, 4)

    version_7 = prediction_log.read_prediction_log(
        log_path,
        max_rows=2,
        model_version="7",
    )
    version_8 = prediction_log.read_prediction_log(
        log_path,
        max_rows=2,
        model_version="8",
    )
    all_rows = prediction_log.read_prediction_log(log_path, max_rows=10)

    assert list(version_7["quality_index"]) == [2.2, 2.3]
    assert list(version_8["quality_index"]) == [3.1, 3.2]
    assert len(all_rows) == 4


def test_append_prediction_log_prunes_stale_model_rows_outside_retention_window(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "prediction-log.jsonl"

    prediction_log.append_prediction_log(
        {
            "model_version": "6",
            "predictions": [
                {
                    "spot_id": "silvaplana",
                    "spot_name": "Silvaplana",
                    "forecast": [
                        {"time": "2025-01-01T00:00:00+00:00", "quality_index": 1.5}
                    ],
                }
            ],
        },
        endpoint="predict",
        path=log_path,
        max_rows=2,
        retention_days=30,
        logged_at=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
    )
    prediction_log.append_prediction_log(
        {
            "model_version": "7",
            "predictions": [
                {
                    "spot_id": "silvaplana",
                    "spot_name": "Silvaplana",
                    "forecast": [
                        {"time": "2025-01-01T01:00:00+00:00", "quality_index": 2.4},
                        {"time": "2025-01-01T02:00:00+00:00", "quality_index": 2.6},
                    ],
                }
            ],
        },
        endpoint="predict",
        path=log_path,
        max_rows=2,
        retention_days=30,
        logged_at=datetime(2026, 2, 15, 10, 0, tzinfo=UTC),
    )

    frame = prediction_log.read_prediction_log(
        log_path,
        max_rows=10,
        retention_days=30,
    )

    assert list(frame["model_version"]) == ["7", "7"]
    assert list(frame["quality_index"]) == [2.4, 2.6]


def test_read_prediction_log_uses_env_configured_max_rows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "prediction-log.jsonl"
    monkeypatch.setenv("FOEHNCAST_PREDICTION_LOG_MAX_ROWS", "2")

    prediction_log.append_prediction_log(
        {
            "model_version": "7",
            "predictions": [
                {
                    "spot_id": "silvaplana",
                    "spot_name": "Silvaplana",
                    "forecast": [
                        {"time": "2025-01-01T00:00:00+00:00", "quality_index": 2.1},
                        {"time": "2025-01-01T01:00:00+00:00", "quality_index": 2.2},
                        {"time": "2025-01-01T02:00:00+00:00", "quality_index": 2.3},
                    ],
                }
            ],
        },
        endpoint="predict",
        path=log_path,
        logged_at=datetime(2026, 5, 11, 10, 0, tzinfo=UTC),
    )

    frame = prediction_log.read_prediction_log(log_path)

    assert len(frame) == 2
    assert list(frame["quality_index"]) == [2.2, 2.3]


def test_read_prediction_log_uses_minimum_two_window_retention_from_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "prediction-log.jsonl"
    monkeypatch.setattr(
        _common_mod,
        "get_monitoring_config",
        lambda: {
            "evaluation_window_days": 30,
            "prediction_log_retention_days": 10,
        },
    )

    prediction_log.append_prediction_log(
        {
            "model_version": "7",
            "predictions": [
                {
                    "spot_id": "silvaplana",
                    "spot_name": "Silvaplana",
                    "forecast": [
                        {"time": "2025-01-01T00:00:00+00:00", "quality_index": 2.1}
                    ],
                }
            ],
        },
        endpoint="predict",
        path=log_path,
        max_rows=2,
        logged_at=datetime(2026, 1, 25, 10, 0, tzinfo=UTC),
    )
    prediction_log.append_prediction_log(
        {
            "model_version": "7",
            "predictions": [
                {
                    "spot_id": "silvaplana",
                    "spot_name": "Silvaplana",
                    "forecast": [
                        {"time": "2025-01-01T01:00:00+00:00", "quality_index": 2.3}
                    ],
                }
            ],
        },
        endpoint="predict",
        path=log_path,
        max_rows=2,
        logged_at=datetime(2026, 2, 14, 10, 0, tzinfo=UTC),
    )

    frame = prediction_log.read_prediction_log(log_path, max_rows=10)

    assert len(frame) == 2
    assert list(frame["quality_index"]) == [2.1, 2.3]


def test_emit_prediction_drift_metrics_filters_to_current_model_version(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "prediction-log.jsonl"
    captured: dict[str, object] = {}

    prediction_log.append_prediction_log(
        {
            "model_version": "6",
            "predictions": [
                {
                    "spot_id": "silvaplana",
                    "spot_name": "Silvaplana",
                    "forecast": [
                        {"time": "2025-01-01T00:00:00+00:00", "quality_index": 1.5}
                    ],
                }
            ],
        },
        endpoint="predict",
        path=log_path,
        logged_at=datetime(2026, 5, 10, 10, 0, tzinfo=UTC),
    )

    def fake_detect_prediction_drift(predictions_log: pd.DataFrame) -> SimpleNamespace:
        captured["rows"] = len(predictions_log)
        captured["versions"] = list(predictions_log["model_version"])
        captured["dataset_name"] = predictions_log.attrs["dataset_name"]
        captured["dataset_version"] = predictions_log.attrs["dataset_version"]
        return SimpleNamespace(
            dataset_name=predictions_log.attrs["dataset_name"],
            dataset_version=predictions_log.attrs["dataset_version"],
        )

    monkeypatch.setattr(
        prediction_log,
        "detect_prediction_drift",
        fake_detect_prediction_drift,
    )
    monkeypatch.setattr(
        prediction_log,
        "push_drift_metrics",
        lambda report: captured.update({"pushed": report}),
    )

    report = prediction_log.emit_prediction_drift_metrics(
        {
            "model_version": "7",
            "predictions": [
                {
                    "spot_id": "silvaplana",
                    "spot_name": "Silvaplana",
                    "forecast": [
                        {"time": "2025-01-01T00:00:00+00:00", "quality_index": 2.4},
                        {"time": "2025-01-01T01:00:00+00:00", "quality_index": 2.6},
                    ],
                }
            ],
        },
        endpoint="predict",
        path=log_path,
    )

    assert report is not None
    assert captured["rows"] == 2
    assert captured["versions"] == ["7", "7"]
    assert captured["dataset_name"] == "inference_predictions"
    assert captured["dataset_version"] == "7"
    assert captured["pushed"].dataset_version == "7"


def test_emit_prediction_drift_metrics_uses_recent_rows_for_current_model_version(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "prediction-log.jsonl"
    captured: dict[str, object] = {}

    def append(model_version: str, quality_index: float, hour: int) -> None:
        prediction_log.append_prediction_log(
            {
                "model_version": model_version,
                "predictions": [
                    {
                        "spot_id": "silvaplana",
                        "spot_name": "Silvaplana",
                        "forecast": [
                            {
                                "time": f"2025-01-01T{hour:02d}:00:00+00:00",
                                "quality_index": quality_index,
                            }
                        ],
                    }
                ],
            },
            endpoint="predict",
            path=log_path,
            max_rows=2,
            logged_at=datetime(2026, 5, 11, 10, hour, tzinfo=UTC),
        )

    append("7", 2.1, 0)
    append("8", 3.1, 1)
    append("8", 3.2, 2)

    def fake_detect_prediction_drift(predictions_log: pd.DataFrame) -> SimpleNamespace:
        captured["rows"] = len(predictions_log)
        captured["versions"] = list(predictions_log["model_version"])
        captured["quality_index"] = list(predictions_log["quality_index"])
        return SimpleNamespace(
            dataset_name=predictions_log.attrs["dataset_name"],
            dataset_version=predictions_log.attrs["dataset_version"],
        )

    monkeypatch.setattr(
        prediction_log,
        "detect_prediction_drift",
        fake_detect_prediction_drift,
    )
    monkeypatch.setattr(
        prediction_log,
        "push_drift_metrics",
        lambda report: captured.update({"pushed": report}),
    )

    report = prediction_log.emit_prediction_drift_metrics(
        {
            "model_version": "7",
            "predictions": [
                {
                    "spot_id": "silvaplana",
                    "spot_name": "Silvaplana",
                    "forecast": [
                        {"time": "2025-01-01T03:00:00+00:00", "quality_index": 2.2}
                    ],
                }
            ],
        },
        endpoint="predict",
        path=log_path,
        max_rows=2,
    )

    assert report is not None
    assert captured["rows"] == 2
    assert captured["versions"] == ["7", "7"]
    assert captured["quality_index"] == [2.1, 2.2]


def test_emit_prediction_drift_metrics_prefers_durable_event_history_when_available(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    shared_event_path = tmp_path / "shared" / "prediction-events.jsonl"
    local_log_path = tmp_path / "instance-a" / "prediction-log.jsonl"
    remote_log_path = tmp_path / "instance-b" / "prediction-log.jsonl"
    captured: dict[str, object] = {}

    prediction_log.append_prediction_log(
        {
            "model_version": "7",
            "predictions": [
                {
                    "spot_id": "silvaplana",
                    "spot_name": "Silvaplana",
                    "forecast": [
                        {"time": "2025-01-01T00:00:00+00:00", "quality_index": 2.1}
                    ],
                }
            ],
        },
        endpoint="predict",
        path=remote_log_path,
        event_path=shared_event_path,
        logged_at=datetime(2026, 5, 11, 9, 0, tzinfo=UTC),
    )

    def fake_detect_prediction_drift(predictions_log: pd.DataFrame) -> SimpleNamespace:
        captured["rows"] = len(predictions_log)
        captured["quality_index"] = list(predictions_log["quality_index"])
        return SimpleNamespace(
            dataset_name=predictions_log.attrs["dataset_name"],
            dataset_version=predictions_log.attrs["dataset_version"],
        )

    monkeypatch.setattr(
        prediction_log,
        "detect_prediction_drift",
        fake_detect_prediction_drift,
    )
    monkeypatch.setattr(
        prediction_log,
        "push_drift_metrics",
        lambda report: captured.update({"pushed": report}),
    )

    report = prediction_log.emit_prediction_drift_metrics(
        {
            "model_version": "7",
            "predictions": [
                {
                    "spot_id": "silvaplana",
                    "spot_name": "Silvaplana",
                    "forecast": [
                        {"time": "2025-01-01T01:00:00+00:00", "quality_index": 2.4}
                    ],
                }
            ],
        },
        endpoint="predict",
        path=local_log_path,
        event_path=shared_event_path,
        max_rows=10,
    )

    assert report is not None
    assert captured["rows"] == 2
    assert captured["quality_index"] == [2.1, 2.4]
    assert captured["pushed"].dataset_version == "7"


def test_append_prediction_log_bigquery_uses_prediction_event_warehouse_contract(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}
    log_path = tmp_path / "prediction-log.jsonl"

    class FakeClient:
        def __init__(self, project: str) -> None:
            captured["project"] = project

        def get_table(self, table_id: str) -> object:
            captured["missing_table_id"] = table_id
            raise KeyError(table_id)

        def load_table_from_dataframe(
            self,
            frame: pd.DataFrame,
            table_id: str,
            job_config: object,
        ) -> FakeCompletedJob:
            captured["table_id"] = table_id
            captured["frame"] = frame.copy()
            captured["write_disposition"] = job_config.write_disposition
            captured["time_partitioning"] = job_config.time_partitioning
            captured["clustering_fields"] = job_config.clustering_fields
            captured["schema_update_options"] = job_config.schema_update_options
            return FakeCompletedJob(lambda: captured.update({"job_completed": True}))

    monkeypatch.setattr(
        _bq_mod,
        "_bigquery_module",
        lambda: types.SimpleNamespace(
            Client=FakeClient,
            LoadJobConfig=FakeLoadJobConfig,
            QueryJobConfig=FakeQueryJobConfig,
            ScalarQueryParameter=FakeScalarQueryParameter,
            SchemaUpdateOption=types.SimpleNamespace(
                ALLOW_FIELD_ADDITION="ALLOW_FIELD_ADDITION"
            ),
            TimePartitioning=FakeTimePartitioning,
            TimePartitioningType=types.SimpleNamespace(DAY="DAY"),
        ),
    )
    _patch_prediction_event_bigquery_not_found(monkeypatch)
    _patch_prediction_event_bigquery_storage_config(monkeypatch)

    prediction_log.append_prediction_log(
        {
            "model_version": "7",
            "predictions": [
                {
                    "spot_id": "silvaplana",
                    "spot_name": "Silvaplana",
                    "forecast": [
                        {"time": "2025-01-01T00:00:00+00:00", "quality_index": 2.4},
                        {"time": "2025-01-01T01:00:00+00:00", "quality_index": 2.8},
                    ],
                }
            ],
        },
        endpoint="predict",
        spot_ids=["silvaplana"],
        path=log_path,
        logged_at=datetime(2026, 5, 11, 10, 0, tzinfo=UTC),
    )

    assert captured["project"] == "demo-project"
    assert (
        captured["missing_table_id"]
        == "demo-project.foehncast_monitoring.prediction_events"
    )
    assert captured["table_id"] == "demo-project.foehncast_monitoring.prediction_events"
    assert captured["write_disposition"] == "WRITE_APPEND"
    assert captured["time_partitioning"].field == "prediction_timestamp"
    assert captured["time_partitioning"].type_ == "DAY"
    assert captured["time_partitioning"].expiration_ms == 15552000000
    assert captured["clustering_fields"] == ["model_version", "endpoint", "spot_id"]
    assert captured["schema_update_options"] == ["ALLOW_FIELD_ADDITION"]
    assert captured["job_completed"] is True
    assert not log_path.with_name("prediction-events.jsonl").exists()

    written = captured["frame"]
    assert list(written["model_version"]) == ["7", "7"]
    assert list(written["endpoint"]) == ["predict", "predict"]
    assert list(written["requested_spot_ids"]) == ['["silvaplana"]', '["silvaplana"]']
    assert log_path.exists()


def test_read_prediction_history_bigquery_uses_warehouse_contract_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    warehouse_frame = pd.DataFrame(
        {
            "prediction_timestamp": pd.to_datetime(
                ["2026-05-11T10:00:00+00:00", "2026-05-11T11:00:00+00:00"],
                utc=True,
            ),
            "forecast_time": pd.to_datetime(
                ["2025-01-01T00:00:00+00:00", "2025-01-01T01:00:00+00:00"],
                utc=True,
            ),
            "quality_index": [2.4, 2.8],
            "endpoint": ["predict", "predict"],
            "model_version": ["7", "7"],
            "spot_id": ["silvaplana", "silvaplana"],
            "spot_name": ["Silvaplana", "Silvaplana"],
            "requested_spot_ids": ['["silvaplana"]', '["silvaplana"]'],
        }
    )

    class FakeClient:
        def __init__(self, project: str) -> None:
            captured["project"] = project

        def get_table(self, table_id: str) -> object:
            captured["table_id"] = table_id
            return object()

        def query(
            self, query: str, job_config: object | None = None
        ) -> _PredictionFrameQueryJob:
            captured["query"] = query
            captured["job_config"] = job_config
            return _PredictionFrameQueryJob(warehouse_frame)

    monkeypatch.setattr(
        _bq_mod,
        "_bigquery_module",
        lambda: types.SimpleNamespace(
            Client=FakeClient,
            QueryJobConfig=FakeQueryJobConfig,
            ScalarQueryParameter=FakeScalarQueryParameter,
        ),
    )
    _patch_prediction_event_bigquery_not_found(monkeypatch)
    _patch_prediction_event_bigquery_storage_config(monkeypatch)

    history = prediction_log.read_prediction_history(max_rows=10, model_version="7")

    assert captured["project"] == "demo-project"
    assert captured["table_id"] == "demo-project.foehncast_monitoring.prediction_events"
    assert "ROW_NUMBER() OVER" in captured["query"]
    parameters = captured["job_config"].query_parameters
    assert [(param.name, param.value) for param in parameters] == [
        ("retention_days", 60),
        ("max_rows", 10),
        ("model_version", "7"),
    ]
    assert list(history["quality_index"]) == [2.4, 2.8]
    assert history["requested_spot_ids"].tolist() == [["silvaplana"], ["silvaplana"]]


def test_emit_prediction_drift_metrics_uses_bigquery_history_when_backend_is_bigquery(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    local_log_path = tmp_path / "instance-a" / "prediction-log.jsonl"
    remote_log_path = tmp_path / "instance-b" / "prediction-log.jsonl"
    captured: dict[str, object] = {}
    state: dict[str, pd.DataFrame | None] = {"table": None}

    class FakeClient:
        def __init__(self, project: str) -> None:
            self.project = project

        def get_table(self, table_id: str) -> object:
            if state["table"] is None:
                raise KeyError(table_id)
            return object()

        def load_table_from_dataframe(
            self,
            frame: pd.DataFrame,
            table_id: str,
            job_config: object,
        ) -> FakeCompletedJob:
            if state["table"] is None:
                state["table"] = frame.copy()
            else:
                state["table"] = pd.concat(
                    [state["table"], frame.copy()],
                    ignore_index=True,
                )
            return FakeCompletedJob()

        def query(
            self, query: str, job_config: object | None = None
        ) -> _PredictionFrameQueryJob:
            parameters = {
                param.name: param.value
                for param in getattr(job_config, "query_parameters", [])
            }
            frame = state["table"]
            if frame is None:
                return _PredictionFrameQueryJob()

            filtered = frame.copy()
            model_version = str(parameters.get("model_version", "")).strip()
            if model_version:
                filtered = filtered.loc[filtered["model_version"] == model_version]
            filtered = filtered.sort_values(
                ["prediction_timestamp", "forecast_time"],
            ).reset_index(drop=True)
            max_rows = int(parameters.get("max_rows", len(filtered)))
            filtered = filtered.tail(max_rows).reset_index(drop=True)
            return _PredictionFrameQueryJob(filtered)

    monkeypatch.setattr(
        _bq_mod,
        "_bigquery_module",
        lambda: types.SimpleNamespace(
            Client=FakeClient,
            LoadJobConfig=FakeLoadJobConfig,
            QueryJobConfig=FakeQueryJobConfig,
            ScalarQueryParameter=FakeScalarQueryParameter,
            SchemaUpdateOption=types.SimpleNamespace(
                ALLOW_FIELD_ADDITION="ALLOW_FIELD_ADDITION"
            ),
            TimePartitioning=FakeTimePartitioning,
            TimePartitioningType=types.SimpleNamespace(DAY="DAY"),
        ),
    )
    _patch_prediction_event_bigquery_not_found(monkeypatch)
    _patch_prediction_event_bigquery_storage_config(monkeypatch)

    prediction_log.append_prediction_log(
        {
            "model_version": "7",
            "predictions": [
                {
                    "spot_id": "silvaplana",
                    "spot_name": "Silvaplana",
                    "forecast": [
                        {"time": "2025-01-01T00:00:00+00:00", "quality_index": 2.1}
                    ],
                }
            ],
        },
        endpoint="predict",
        path=remote_log_path,
        logged_at=datetime(2026, 5, 11, 9, 0, tzinfo=UTC),
    )

    def fake_detect_prediction_drift(predictions_log: pd.DataFrame) -> SimpleNamespace:
        captured["rows"] = len(predictions_log)
        captured["quality_index"] = list(predictions_log["quality_index"])
        return SimpleNamespace(
            dataset_name=predictions_log.attrs["dataset_name"],
            dataset_version=predictions_log.attrs["dataset_version"],
        )

    monkeypatch.setattr(
        prediction_log,
        "detect_prediction_drift",
        fake_detect_prediction_drift,
    )
    monkeypatch.setattr(
        prediction_log,
        "push_drift_metrics",
        lambda report: captured.update({"pushed": report}),
    )

    report = prediction_log.emit_prediction_drift_metrics(
        {
            "model_version": "7",
            "predictions": [
                {
                    "spot_id": "silvaplana",
                    "spot_name": "Silvaplana",
                    "forecast": [
                        {"time": "2025-01-01T01:00:00+00:00", "quality_index": 2.4}
                    ],
                }
            ],
        },
        endpoint="predict",
        path=local_log_path,
        max_rows=10,
    )

    assert report is not None
    assert captured["rows"] == 2
    assert captured["quality_index"] == [2.1, 2.4]
    assert captured["pushed"].dataset_version == "7"


def test_emit_prediction_drift_metrics_returns_none_when_no_forecast_rows(
    tmp_path: Path,
) -> None:
    report = prediction_log.emit_prediction_drift_metrics(
        {
            "model_version": "7",
            "predictions": [
                {
                    "spot_id": "silvaplana",
                    "spot_name": "Silvaplana",
                    "forecast": [],
                }
            ],
        },
        endpoint="predict",
        path=tmp_path / "prediction-log.jsonl",
    )

    assert report is None
