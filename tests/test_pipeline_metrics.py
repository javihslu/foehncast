"""Tests for feature-pipeline monitoring helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from foehncast.monitoring import pipeline_metrics


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


def test_emit_feature_pipeline_run_summary_writes_json_and_logs_mlflow(
    monkeypatch,
    tmp_path: Path,
) -> None:
    logged: dict[str, object] = {}

    class FakeMlflow:
        def active_run(self) -> object:
            return object()

        def log_metrics(self, metrics: dict[str, float]) -> None:
            logged["metrics"] = metrics

        def log_artifact(self, path: str, artifact_path: str | None = None) -> None:
            logged["artifact"] = (path, artifact_path)

    monkeypatch.setattr(pipeline_metrics, "_DEFAULT_REPORT_DIR", tmp_path)
    monkeypatch.setattr(pipeline_metrics, "mlflow", FakeMlflow())

    summary = {
        "dataset": "notebook_eval",
        "expected_spot_count": 1,
        "fetched_spot_count": 1,
        "stored_spot_count": 1,
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
    assert json.loads(summary_path.read_text())["dataset"] == "notebook_eval"
    assert logged["artifact"] == (
        str(summary_path),
        "monitoring/feature_pipeline",
    )
    assert logged["metrics"]["feature_stored_spot_count"] == 1.0
    assert logged["metrics"]["feature_silvaplana_feast_projection_ready"] == 1.0


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
