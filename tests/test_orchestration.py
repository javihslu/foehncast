"""Tests for Airflow orchestration helpers."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from foehncast import orchestration


def test_run_feature_pipeline_fetches_validated_features(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    feature_df = pd.DataFrame(
        {
            "wind_speed_10m": [14.0],
            "wind_gusts_10m": [18.0],
            "wind_direction_10m": [220.0],
        }
    )
    stored: list[tuple[str, str]] = []

    monkeypatch.setattr(
        orchestration,
        "get_spots",
        lambda: [
            {
                "id": "silvaplana",
                "shore_orientation_deg": 225,
            }
        ],
    )
    monkeypatch.setattr(
        orchestration,
        "fetch_all_spots",
        lambda: {"silvaplana": feature_df},
    )
    monkeypatch.setattr(
        orchestration,
        "engineer_features",
        lambda df, shore_orientation_deg: df.assign(gust_factor=1.2),
    )
    monkeypatch.setattr(
        orchestration,
        "run_validation",
        lambda df, spot_id: SimpleNamespace(is_valid=True),
    )
    monkeypatch.setattr(
        orchestration,
        "write_features",
        lambda df, spot_id, dataset: stored.append((spot_id, dataset)),
    )

    stored_spots = orchestration.run_feature_pipeline()

    assert stored_spots == ["silvaplana"]
    assert stored == [("silvaplana", "train")]


def test_run_feature_pipeline_raises_on_validation_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        orchestration,
        "get_spots",
        lambda: [{"id": "silvaplana", "shore_orientation_deg": 225}],
    )
    monkeypatch.setattr(
        orchestration,
        "fetch_all_spots",
        lambda: {"silvaplana": pd.DataFrame({"wind_speed_10m": [14.0]})},
    )
    monkeypatch.setattr(
        orchestration,
        "engineer_features",
        lambda df, shore_orientation_deg: df,
    )
    monkeypatch.setattr(
        orchestration,
        "run_validation",
        lambda df, spot_id: SimpleNamespace(is_valid=False),
    )

    with pytest.raises(ValueError, match="Feature validation failed"):
        orchestration.run_feature_pipeline()


def test_evaluate_training_run_logs_to_existing_mlflow_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    logged: dict[str, object] = {}

    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)

    class FakeRun:
        def __enter__(self) -> FakeRun:
            logged["entered"] = True
            return self

        def __exit__(self, exc_type, exc, exc_tb) -> None:
            return None

    class FakeClient:
        def get_run(self, run_id: str) -> SimpleNamespace:
            logged["queried_run_id"] = run_id
            return SimpleNamespace(data=SimpleNamespace(metrics={"mae": 0.5}))

    class FakeMlflow:
        def MlflowClient(self) -> FakeClient:
            return FakeClient()

        def set_tracking_uri(self, tracking_uri: str) -> None:
            logged["tracking_uri"] = tracking_uri

        def start_run(self, run_id: str) -> FakeRun:
            logged["run_id"] = run_id
            return FakeRun()

    monkeypatch.setattr(orchestration, "mlflow", FakeMlflow())
    monkeypatch.setattr(
        orchestration,
        "get_mlflow_tracking_uri",
        lambda: "http://localhost:5001",
    )
    monkeypatch.setattr(
        orchestration,
        "generate_evaluation_report",
        lambda metrics, output_path: str(tmp_path / "evaluation.md"),
    )

    report_path = orchestration.evaluate_training_run("run-123")

    assert report_path == str(tmp_path / "evaluation.md")
    assert logged["tracking_uri"] == "http://localhost:5001"
    assert logged["queried_run_id"] == "run-123"
    assert logged["run_id"] == "run-123"


def test_register_training_run_registers_and_promotes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logged: dict[str, object] = {}

    monkeypatch.setattr(
        orchestration,
        "register_model",
        lambda run_id: SimpleNamespace(version="7"),
    )
    monkeypatch.setattr(
        orchestration,
        "promote_model",
        lambda model_name, version, stage="Production": logged.update(
            {"promotion": (model_name, version, stage)}
        ),
    )

    version = orchestration.register_training_run("run-456")

    assert version == "7"
    assert logged["promotion"] == (None, "7", "Production")
