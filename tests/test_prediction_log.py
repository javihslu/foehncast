"""Tests for prediction log persistence and drift monitoring."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from foehncast.monitoring import prediction_log


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
        prediction_log,
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
