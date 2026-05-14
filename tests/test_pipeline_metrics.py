"""Tests for feature-pipeline monitoring helpers."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from foehncast.monitoring import pipeline_metrics


class _ArtifactLoggingMlflow:
    def __init__(self, logged: dict[str, object]) -> None:
        self._logged = logged

    def active_run(self) -> object:
        return object()

    def log_metrics(self, metrics: dict[str, float]) -> None:
        self._logged["metrics"] = metrics

    def log_artifact(self, path: str, artifact_path: str | None = None) -> None:
        self._logged["artifact"] = (path, artifact_path)


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text())


def test_build_feature_pipeline_spot_summary_captures_ingest_unit_contract() -> None:
    forecast_df = pd.DataFrame(
        {
            "wind_speed_10m": [24.0],
            "wind_gusts_10m": [30.0],
        },
        index=pd.to_datetime(["2026-05-06T00:00:00Z"]),
    )
    forecast_df.index.name = "time"
    forecast_df.attrs["hourly_units"] = {
        "wind_speed_10m": "km/h",
        "wind_gusts_10m": "km/h",
    }

    summary = pipeline_metrics.build_feature_pipeline_spot_summary(
        spot_id="silvaplana",
        forecast_df=forecast_df,
        status="stored",
    )

    assert summary["ingest"]["wind_speed_10m_unit"] == "km/h"
    assert summary["ingest"]["wind_gusts_10m_unit"] == "km/h"
    assert summary["ingest"]["source_unit_contract_confirmed"] is True
    assert summary["ingest"]["hourly_units"]["wind_speed_10m"] == "km/h"


def test_build_feature_pipeline_spot_summary_normalizes_validation_fields() -> None:
    forecast_df = pd.DataFrame(
        {
            "wind_speed_10m": [24.0],
            "wind_gusts_10m": [30.0],
        },
        index=pd.to_datetime(["2026-05-06T00:00:00Z"]),
    )

    summary = pipeline_metrics.build_feature_pipeline_spot_summary(
        spot_id="silvaplana",
        forecast_df=forecast_df,
        validation=SimpleNamespace(
            is_valid=False,
            missing_columns=("shore_alignment",),
            null_fractions={"gust_factor": 0.25},
            range_violations=pd.DataFrame(
                [
                    {
                        "column": "wind_speed_10m",
                        "index": "row-1",
                        "value": 300.0,
                        "min": 0.0,
                        "max": 200.0,
                    }
                ]
            ),
        ),
        status="validated",
    )

    assert summary["validation"]["is_valid"] is False
    assert summary["validation"]["missing_column_count"] == 1
    assert summary["validation"]["missing_columns"] == ["shore_alignment"]
    assert summary["validation"]["max_null_fraction"] == 0.25
    assert summary["validation"]["range_violation_count"] == 1


def test_emit_feature_pipeline_run_summary_writes_json_and_logs_mlflow(
    monkeypatch,
    tmp_path: Path,
) -> None:
    logged: dict[str, object] = {}

    monkeypatch.setattr(pipeline_metrics, "_default_report_dir", lambda: tmp_path)
    monkeypatch.setattr(pipeline_metrics, "mlflow", _ArtifactLoggingMlflow(logged))

    summary = {
        "dataset": "notebook_eval",
        "expected_spot_count": 1,
        "fetched_spot_count": 1,
        "engineered_spot_count": 1,
        "validated_spot_count": 1,
        "stored_spot_count": 1,
        "stage_durations_seconds": {"fetch": 12.5, "store": 3.5},
        "stage_failure_counts": {
            "fetch": 0,
            "engineer": 0,
            "validate": 0,
            "store": 0,
        },
        "skipped_spot_count": 0,
        "failed_spot_count": 0,
        "spots": [
            {
                "spot_id": "silvaplana",
                "status": "stored",
                "error": None,
                "ingest": {"rows": 24, "column_count": 3},
                "engineering": {"rows": 24},
                "validation": {"is_valid": True, "range_violation_count": 0},
                "storage": {"stored_rows": 24, "max_numeric_abs_delta": 0.0},
                "feast": {"projection_ready": True},
            }
        ],
    }

    summary_path = pipeline_metrics.emit_feature_pipeline_run_summary(summary)

    assert summary_path == tmp_path / "feature-pipeline-notebook_eval-latest.json"
    assert _read_json(summary_path)["dataset"] == "notebook_eval"
    assert logged["artifact"] == (
        str(summary_path),
        "monitoring/feature_pipeline",
    )
    assert logged["metrics"]["feature_stored_spot_count"] == 1.0
    assert logged["metrics"]["feature_engineered_spot_count"] == 1.0
    assert logged["metrics"]["feature_validated_spot_count"] == 1.0
    assert logged["metrics"]["feature_fetch_duration_seconds"] == 12.5
    assert logged["metrics"]["feature_store_duration_seconds"] == 3.5
    assert logged["metrics"]["feature_validate_failure_count"] == 0.0
    assert logged["metrics"]["feature_silvaplana_feast_projection_ready"] == 1.0
    history_paths = pipeline_metrics.feature_pipeline_summary_history_paths(
        dataset="notebook_eval"
    )
    assert len(history_paths) == 1
    assert _read_json(history_paths[0])["dataset"] == "notebook_eval"


def test_feature_pipeline_stage_overview_flattens_summary() -> None:
    summary = {
        "spots": [
            {
                "spot_id": "silvaplana",
                "status": "stored",
                "error": None,
                "ingest": {
                    "rows": 24,
                    "wind_speed_10m_unit": "km/h",
                    "wind_gusts_10m_unit": "km/h",
                    "source_unit_contract_confirmed": True,
                },
                "engineering": {"rows": 24, "engineered_column_count": 7},
                "validation": {"is_valid": True, "range_violation_count": 0},
                "storage": {
                    "stored_rows": 24,
                    "max_numeric_abs_delta": 0.0,
                    "time_basis_preserved": True,
                },
                "feast": {
                    "projection_ready": True,
                    "event_timestamp_source": "datetime_index",
                },
            }
        ]
    }

    overview = pipeline_metrics.feature_pipeline_stage_overview(summary)

    assert list(overview["spot_id"]) == ["silvaplana"]
    assert list(overview["ingest_rows"]) == [24]
    assert list(overview["wind_speed_10m_unit"]) == ["km/h"]
    assert list(overview["source_unit_contract_confirmed"]) == [True]
    assert list(overview["feast_projection_ready"]) == [True]


def test_emit_training_pipeline_run_summary_writes_json_and_logs_mlflow(
    monkeypatch,
    tmp_path: Path,
) -> None:
    logged: dict[str, object] = {}

    monkeypatch.setattr(pipeline_metrics, "_default_report_dir", lambda: tmp_path)
    monkeypatch.setattr(pipeline_metrics, "mlflow", _ArtifactLoggingMlflow(logged))

    summary = {
        "dataset": "train",
        "requested_stage": "Production",
        "training_run_id": "run-123",
        "training_row_count": 240,
        "training_feature_count": 18,
        "train_row_count": 180,
        "test_row_count": 60,
        "evaluation_report_exists": True,
        "registered_model_version": "7",
        "stage_durations_seconds": {"train": 8.5, "evaluate": 1.2},
        "stage_failure_counts": {"train": 0, "evaluate": 0, "register": 0},
        "run_metrics": {"mae": 0.5, "r2": 0.8},
    }

    summary_path = pipeline_metrics.emit_training_pipeline_run_summary(summary)

    assert summary_path == tmp_path / "training-pipeline-train-latest.json"
    assert _read_json(summary_path)["training_run_id"] == "run-123"
    assert logged["artifact"] == (
        str(summary_path),
        "monitoring/training_pipeline",
    )
    assert logged["metrics"]["training_row_count"] == 240.0
    assert logged["metrics"]["training_train_duration_seconds"] == 8.5
    assert logged["metrics"]["training_metric_mae"] == 0.5
    assert logged["metrics"]["training_model_registered"] == 1.0
    history_paths = pipeline_metrics.training_pipeline_summary_history_paths(
        dataset="train"
    )
    assert len(history_paths) == 1
    assert _read_json(history_paths[0])["training_run_id"] == "run-123"


def test_feature_pipeline_summary_history_preserves_latest_contract(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(pipeline_metrics, "_default_report_dir", lambda: tmp_path)

    first_summary = {
        "dataset": "train",
        "generated_at": "2026-05-12T10:00:00+00:00",
        "expected_spot_count": 1,
        "fetched_spot_count": 1,
        "engineered_spot_count": 1,
        "validated_spot_count": 1,
        "stored_spot_count": 1,
        "stage_durations_seconds": {},
        "stage_failure_counts": {},
        "skipped_spot_count": 0,
        "failed_spot_count": 0,
        "spots": [],
    }
    second_summary = {
        **first_summary,
        "generated_at": "2026-05-12T11:00:00+00:00",
        "stored_spot_count": 2,
    }

    latest_path = pipeline_metrics.write_feature_pipeline_run_summary(first_summary)
    pipeline_metrics.write_feature_pipeline_run_summary(second_summary)

    assert latest_path == tmp_path / "feature-pipeline-train-latest.json"
    assert _read_json(latest_path)["stored_spot_count"] == 2
    assert [
        path.name
        for path in pipeline_metrics.feature_pipeline_summary_history_paths("train")
    ] == [
        "feature-pipeline-train-20260512T100000000000Z.json",
        "feature-pipeline-train-20260512T110000000000Z.json",
    ]
    assert [
        summary["stored_spot_count"]
        for summary in pipeline_metrics.read_feature_pipeline_run_summary_history(
            "train"
        )
    ] == [1, 2]


def test_training_pipeline_summary_history_preserves_latest_contract(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(pipeline_metrics, "_default_report_dir", lambda: tmp_path)

    first_summary = {
        "dataset": "train",
        "generated_at": "2026-05-12T10:00:00+00:00",
        "requested_stage": "Candidate",
        "training_run_id": "run-100",
        "training_row_count": 240,
        "training_feature_count": 18,
        "train_row_count": 180,
        "test_row_count": 60,
        "evaluation_report_exists": True,
        "registered_model_version": "7",
        "stage_durations_seconds": {},
        "stage_failure_counts": {},
        "run_metrics": {},
    }
    second_summary = {
        **first_summary,
        "generated_at": "2026-05-12T11:00:00+00:00",
        "training_run_id": "run-101",
    }

    latest_path = pipeline_metrics.write_training_pipeline_run_summary(first_summary)
    pipeline_metrics.write_training_pipeline_run_summary(second_summary)

    assert latest_path == tmp_path / "training-pipeline-train-latest.json"
    assert _read_json(latest_path)["training_run_id"] == "run-101"
    assert [
        path.name
        for path in pipeline_metrics.training_pipeline_summary_history_paths("train")
    ] == [
        "training-pipeline-train-20260512T100000000000Z.json",
        "training-pipeline-train-20260512T110000000000Z.json",
    ]
    assert [
        summary["training_run_id"]
        for summary in pipeline_metrics.read_training_pipeline_run_summary_history(
            "train"
        )
    ] == ["run-100", "run-101"]


def test_training_pipeline_stage_overview_flattens_summary() -> None:
    summary = {
        "dataset": "train",
        "requested_stage": "Production",
        "training_run_id": "run-123",
        "registered_model_version": "9",
        "stage_states": {
            "train": "succeeded",
            "evaluate": "succeeded",
            "register": "not_run",
        },
        "stage_durations_seconds": {"train": 10.0, "evaluate": 2.0},
        "stage_failure_counts": {"train": 0, "evaluate": 0, "register": 0},
    }

    overview = pipeline_metrics.training_pipeline_stage_overview(summary)

    assert list(overview["stage"]) == ["train", "evaluate", "register"]
    assert list(overview["state"]) == ["succeeded", "succeeded", "not_run"]
    assert list(overview["requested_stage"]) == [
        "Production",
        "Production",
        "Production",
    ]
