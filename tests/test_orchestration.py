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
    emitted: dict[str, object] = {}

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
        lambda df, spot_id: SimpleNamespace(
            is_valid=True,
            missing_columns=[],
            null_fractions={"wind_speed_10m": 0.0},
            range_violations=pd.DataFrame(),
        ),
    )
    monkeypatch.setattr(
        orchestration,
        "write_features",
        lambda df, spot_id, dataset: stored.append((spot_id, dataset)),
    )
    monkeypatch.setattr(
        orchestration,
        "read_features",
        lambda spot_id, dataset: feature_df.assign(gust_factor=1.2),
    )
    monkeypatch.setattr(
        orchestration,
        "emit_feature_pipeline_run_summary",
        lambda summary: emitted.update({"summary": summary}),
    )

    stored_spots = orchestration.run_feature_pipeline()

    assert stored_spots == ["silvaplana"]
    assert stored == [("silvaplana", "train")]
    assert emitted["summary"]["run_status"] == "succeeded"
    assert emitted["summary"]["stored_spot_count"] == 1
    assert emitted["summary"]["spots"][0]["storage"]["stored_rows"] == 1
    assert emitted["summary"]["spots"][0]["feast"]["projection_ready"] is False


def test_run_feature_pipeline_raises_on_validation_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    emitted: dict[str, object] = {}

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
        lambda df, spot_id: SimpleNamespace(
            is_valid=False,
            missing_columns=["gust_factor"],
            null_fractions={"wind_speed_10m": 0.0},
            range_violations=pd.DataFrame(),
        ),
    )
    monkeypatch.setattr(
        orchestration,
        "emit_feature_pipeline_run_summary",
        lambda summary: emitted.update({"summary": summary}),
    )

    with pytest.raises(ValueError, match="Feature validation failed"):
        orchestration.run_feature_pipeline()

    assert emitted["summary"]["run_status"] == "failed"
    assert emitted["summary"]["failed_spot_count"] == 1
    assert emitted["summary"]["spots"][0]["validation"]["is_valid"] is False


def test_run_feature_pipeline_emits_failed_summary_on_ingest_contract_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    emitted: dict[str, object] = {}

    monkeypatch.setattr(
        orchestration,
        "get_spots",
        lambda: [{"id": "silvaplana", "shore_orientation_deg": 225}],
    )
    monkeypatch.setattr(
        orchestration,
        "fetch_all_spots",
        lambda: (_ for _ in ()).throw(
            ValueError("Unexpected unit for wind_speed_10m: expected km/h, got 'kn'")
        ),
    )
    monkeypatch.setattr(
        orchestration,
        "emit_feature_pipeline_run_summary",
        lambda summary: emitted.update({"summary": summary}),
    )

    with pytest.raises(ValueError, match="Unexpected unit for wind_speed_10m"):
        orchestration.run_feature_pipeline()

    assert emitted["summary"]["run_status"] == "failed"
    assert emitted["summary"]["error"] == (
        "Unexpected unit for wind_speed_10m: expected km/h, got 'kn'"
    )
    assert emitted["summary"]["fetched_spot_count"] == 0
    assert emitted["summary"]["spots"] == []


def test_run_feature_pipeline_job_without_mlflow_env_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)

    def fake_run_feature_pipeline(dataset: str = "train") -> list[str]:
        captured["dataset"] = dataset
        return ["silvaplana"]

    monkeypatch.setattr(
        orchestration,
        "run_feature_pipeline",
        fake_run_feature_pipeline,
    )

    stored_spots = orchestration.run_feature_pipeline_job(dataset="validation")

    assert stored_spots == ["silvaplana"]
    assert captured["dataset"] == "validation"


def test_run_feature_pipeline_job_logs_to_mlflow_when_env_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logged: dict[str, object] = {}

    class FakeRun:
        def __enter__(self) -> FakeRun:
            logged["entered"] = True
            return self

        def __exit__(self, exc_type, exc, exc_tb) -> None:
            return None

    class FakeMlflow:
        def set_tracking_uri(self, tracking_uri: str) -> None:
            logged["tracking_uri"] = tracking_uri

        def set_experiment(self, experiment_name: str) -> None:
            logged["experiment_name"] = experiment_name

        def start_run(self, run_name: str) -> FakeRun:
            logged["run_name"] = run_name
            return FakeRun()

        def log_params(self, params: dict[str, object]) -> None:
            logged["params"] = params

        def log_metric(self, name: str, value: float) -> None:
            logged.setdefault("metrics", {})[name] = value

    monkeypatch.setenv("MLFLOW_TRACKING_URI", "https://mlflow.example.com")
    monkeypatch.setattr(orchestration, "mlflow", FakeMlflow())
    monkeypatch.setattr(
        orchestration,
        "get_mlflow_config",
        lambda: {"experiment_name": "foehncast"},
    )
    monkeypatch.setattr(
        orchestration,
        "get_storage_config",
        lambda: {"backend": "bigquery"},
    )
    monkeypatch.setattr(
        orchestration,
        "run_feature_pipeline",
        lambda dataset="train": ["silvaplana", "urnersee"],
    )

    stored_spots = orchestration.run_feature_pipeline_job(dataset="train")

    assert stored_spots == ["silvaplana", "urnersee"]
    assert logged["tracking_uri"] == "https://mlflow.example.com"
    assert logged["experiment_name"] == "foehncast"
    assert logged["run_name"] == "feature-train-refresh"
    assert logged["params"] == {
        "dataset": "train",
        "storage_backend": "bigquery",
        "stored_spots": "silvaplana,urnersee",
    }
    assert logged["metrics"] == {"stored_spot_count": 2}


def test_resolve_airflow_schedule_uses_default_when_env_is_missing() -> None:
    assert (
        orchestration.resolve_airflow_schedule(None, default="0 */6 * * *")
        == "0 */6 * * *"
    )


@pytest.mark.parametrize("schedule", ["", " none ", "manual", "OFF", "false"])
def test_resolve_airflow_schedule_supports_explicit_opt_out(schedule: str) -> None:
    assert (
        orchestration.resolve_airflow_schedule(schedule, default="0 */6 * * *") is None
    )


def test_resolve_airflow_schedule_preserves_explicit_cron() -> None:
    assert orchestration.resolve_airflow_schedule("15 * * * *") == "15 * * * *"


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
