"""Tests for Airflow orchestration helpers."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from foehncast import orchestration
from foehncast.orchestration import drift as _orch_drift
from foehncast.orchestration import feature as _orch_feature
from foehncast.orchestration import training as _orch_training
from tests.mlflow_fixtures import clear_tracking_uri_env


@pytest.fixture(autouse=True)
def _feature_pipeline_state_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        _orch_feature,
        "_feature_pipeline_state_root",
        lambda: tmp_path / "feature-pipeline-state",
    )


class _LoggedRun:
    def __init__(self, logged: dict[str, object]) -> None:
        self.logged = logged

    def __enter__(self) -> _LoggedRun:
        self.logged["entered"] = True
        return self

    def __exit__(self, exc_type, exc, exc_tb) -> None:
        return None


class _FeatureJobMlflow:
    def __init__(self, logged: dict[str, object]) -> None:
        self._logged = logged

    def set_tracking_uri(self, tracking_uri: str) -> None:
        self._logged["tracking_uri"] = tracking_uri

    def set_experiment(self, experiment_name: str) -> None:
        self._logged["experiment_name"] = experiment_name

    def start_run(self, run_name: str) -> _LoggedRun:
        self._logged["run_name"] = run_name
        return _LoggedRun(self._logged)

    def log_params(self, params: dict[str, object]) -> None:
        self._logged["params"] = params

    def log_metric(self, name: str, value: float) -> None:
        self._logged.setdefault("metrics", {})[name] = value


class _QueriedRunClient:
    def __init__(
        self,
        run: SimpleNamespace,
        logged: dict[str, object] | None = None,
    ) -> None:
        self._run = run
        self._logged = logged

    def get_run(self, run_id: str) -> SimpleNamespace:
        if self._logged is not None:
            self._logged["queried_run_id"] = run_id
        return self._run


class _QueriedRunMlflow:
    def __init__(
        self,
        run: SimpleNamespace,
        logged: dict[str, object] | None = None,
    ) -> None:
        self._client = _QueriedRunClient(run, logged)
        self._logged = logged

    def MlflowClient(self) -> _QueriedRunClient:
        return self._client

    def set_tracking_uri(self, tracking_uri: str) -> None:
        if self._logged is not None:
            self._logged["tracking_uri"] = tracking_uri

    def start_run(self, run_id: str) -> _LoggedRun:
        if self._logged is None:
            raise AssertionError("start_run logging requires a logged dictionary")
        self._logged["run_id"] = run_id
        return _LoggedRun(self._logged)


def _capture_emitted_summary(
    monkeypatch: pytest.MonkeyPatch,
    attribute_name: str,
    emitted: dict[str, object],
    *,
    target=None,
) -> None:
    module = target if target is not None else orchestration
    monkeypatch.setattr(
        module,
        attribute_name,
        lambda summary: emitted.update({"summary": summary}),
    )


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
        _orch_feature,
        "get_spots",
        lambda: [
            {
                "id": "silvaplana",
                "shore_orientation_deg": 225,
            }
        ],
    )
    monkeypatch.setattr(
        _orch_feature,
        "fetch_all_spots",
        lambda: {"silvaplana": feature_df},
    )
    monkeypatch.setattr(
        _orch_feature,
        "engineer_features",
        lambda df, shore_orientation_deg: df.assign(gust_factor=1.2),
    )
    monkeypatch.setattr(
        _orch_feature,
        "run_validation",
        lambda df, spot_id: SimpleNamespace(
            is_valid=True,
            missing_columns=[],
            null_fractions={"wind_speed_10m": 0.0},
            range_violations=pd.DataFrame(),
        ),
    )
    monkeypatch.setattr(
        _orch_feature,
        "write_features",
        lambda df, spot_id, dataset: stored.append((spot_id, dataset)),
    )

    read_calls = 0

    def fake_read_features(spot_id: str, dataset: str) -> pd.DataFrame:
        nonlocal read_calls
        read_calls += 1
        if read_calls == 1:
            raise FileNotFoundError("No stored feature rows yet")
        return feature_df.assign(gust_factor=1.2)

    monkeypatch.setattr(
        _orch_feature,
        "read_features",
        fake_read_features,
    )
    monkeypatch.setattr(
        _orch_feature, "detect_data_drift", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(_orch_feature, "push_drift_metrics", lambda report: None)
    _capture_emitted_summary(
        monkeypatch,
        "emit_feature_pipeline_run_summary",
        emitted,
        target=_orch_feature,
    )

    stored_spots = orchestration.run_feature_pipeline()

    assert stored_spots == ["silvaplana"]
    assert stored == [("silvaplana", "train")]
    assert emitted["summary"]["run_status"] == "succeeded"
    assert emitted["summary"]["stored_spot_count"] == 1
    assert emitted["summary"]["spots"][0]["storage"]["stored_rows"] == 1
    assert emitted["summary"]["spots"][0]["feast"]["projection_ready"] is False


def test_run_feature_pipeline_emits_drift_metrics_when_previous_slice_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    forecast_df = pd.DataFrame(
        {
            "wind_speed_10m": [12.0, 13.0],
            "wind_gusts_10m": [16.0, 17.0],
            "wind_direction_10m": [220.0, 221.0],
        }
    )
    previous_stored_df = pd.DataFrame(
        {
            "wind_speed_10m": [10.0, 11.0],
            "wind_gusts_10m": [14.0, 15.0],
            "wind_direction_10m": [218.0, 219.0],
            "gust_factor": [1.1, 1.15],
        }
    )
    current_stored_df = pd.DataFrame(
        {
            "wind_speed_10m": [12.0, 13.0],
            "wind_gusts_10m": [16.0, 17.0],
            "wind_direction_10m": [220.0, 221.0],
            "gust_factor": [1.2, 1.25],
        }
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        _orch_feature,
        "get_spots",
        lambda: [{"id": "silvaplana", "shore_orientation_deg": 225}],
    )
    monkeypatch.setattr(
        _orch_feature,
        "fetch_all_spots",
        lambda: {"silvaplana": forecast_df},
    )
    monkeypatch.setattr(
        _orch_feature,
        "engineer_features",
        lambda df, shore_orientation_deg: df.assign(gust_factor=[1.2, 1.25]),
    )
    monkeypatch.setattr(
        _orch_feature,
        "run_validation",
        lambda df, spot_id: SimpleNamespace(
            is_valid=True,
            missing_columns=[],
            null_fractions={"wind_speed_10m": 0.0},
            range_violations=pd.DataFrame(),
        ),
    )
    monkeypatch.setattr(
        _orch_feature, "write_features", lambda df, spot_id, dataset: None
    )

    read_calls = 0

    def fake_read_features(spot_id: str, dataset: str) -> pd.DataFrame:
        nonlocal read_calls
        read_calls += 1
        if read_calls == 1:
            return previous_stored_df
        return current_stored_df

    monkeypatch.setattr(_orch_feature, "read_features", fake_read_features)
    monkeypatch.setattr(
        _orch_feature,
        "detect_data_drift",
        lambda reference_df, current_df, threshold=None: (
            captured.update(
                {
                    "reference_attrs": dict(reference_df.attrs),
                    "current_attrs": dict(current_df.attrs),
                    "reference_rows": len(reference_df),
                    "current_rows": len(current_df),
                }
            )
            or SimpleNamespace(
                dataset_name="silvaplana",
                dataset_version="train",
                dataset_drift=True,
            )
        ),
    )
    monkeypatch.setattr(
        _orch_feature,
        "push_drift_metrics",
        lambda report: captured.update({"pushed_report": report}),
    )
    monkeypatch.setattr(
        _orch_feature,
        "emit_feature_pipeline_run_summary",
        lambda summary: None,
    )

    stored_spots = orchestration.run_feature_pipeline(dataset="train")

    assert stored_spots == ["silvaplana"]
    assert captured["reference_attrs"] == {
        "dataset_name": "silvaplana",
        "dataset_version": "train",
    }
    assert captured["current_attrs"] == {
        "dataset_name": "silvaplana",
        "dataset_version": "train",
    }
    assert captured["reference_rows"] == 2
    assert captured["current_rows"] == 2
    assert captured["pushed_report"].dataset_name == "silvaplana"


def test_run_feature_pipeline_raises_on_validation_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    emitted: dict[str, object] = {}

    monkeypatch.setattr(
        _orch_feature,
        "get_spots",
        lambda: [{"id": "silvaplana", "shore_orientation_deg": 225}],
    )
    monkeypatch.setattr(
        _orch_feature,
        "fetch_all_spots",
        lambda: {"silvaplana": pd.DataFrame({"wind_speed_10m": [14.0]})},
    )
    monkeypatch.setattr(
        _orch_feature,
        "engineer_features",
        lambda df, shore_orientation_deg: df,
    )
    monkeypatch.setattr(
        _orch_feature,
        "run_validation",
        lambda df, spot_id: SimpleNamespace(
            is_valid=False,
            missing_columns=["gust_factor"],
            null_fractions={"wind_speed_10m": 0.0},
            range_violations=pd.DataFrame(),
        ),
    )
    _capture_emitted_summary(
        monkeypatch,
        "emit_feature_pipeline_run_summary",
        emitted,
        target=_orch_feature,
    )

    with pytest.raises(ValueError, match="Feature validation failed"):
        orchestration.run_feature_pipeline()

    assert emitted["summary"]["run_status"] == "failed"
    assert emitted["summary"]["failed_spot_count"] == 1
    assert emitted["summary"]["stage_failure_counts"]["validate"] == 1
    assert emitted["summary"]["spots"][0]["validation"]["is_valid"] is False


def test_validate_feature_pipeline_context_serializes_timestamp_range_violations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    emitted: dict[str, object] = {}
    feature_df = pd.DataFrame(
        {
            "wind_speed_10m": [14.0],
            "wind_gusts_10m": [18.0],
            "wind_direction_10m": [220.0],
        },
        index=pd.to_datetime(["2026-05-12T09:38:51Z"]),
    )

    monkeypatch.setattr(
        _orch_feature,
        "get_spots",
        lambda: [{"id": "silvaplana", "shore_orientation_deg": 225}],
    )

    feature_context = orchestration._feature_pipeline_context(run_key="timestamp-test")
    feature_context.engineered_spots = ["silvaplana"]
    run_dir = feature_context.run_dir
    orchestration._write_feature_pipeline_frame(
        orchestration._feature_pipeline_stage_path(run_dir, "feature", "silvaplana"),
        feature_df,
    )

    monkeypatch.setattr(
        _orch_feature,
        "run_validation",
        lambda df, spot_id: SimpleNamespace(
            is_valid=False,
            missing_columns=[],
            null_fractions={"wind_speed_10m": 0.0},
            range_violations=pd.DataFrame(
                [
                    {
                        "column": "wind_speed_10m",
                        "index": pd.Timestamp("2026-05-12T09:38:51Z"),
                        "value": 300.0,
                        "min": 0.0,
                        "max": 200.0,
                    }
                ]
            ),
        ),
    )
    _capture_emitted_summary(
        monkeypatch,
        "emit_feature_pipeline_run_summary",
        emitted,
        target=_orch_feature,
    )

    with pytest.raises(ValueError, match="Feature validation failed"):
        orchestration.validate_feature_pipeline_context(feature_context.to_payload())

    validation_path = orchestration._feature_pipeline_validation_path(
        run_dir, "silvaplana"
    )
    payload = json.loads(validation_path.read_text())

    assert payload["range_violations"][0]["index"] == "2026-05-12T09:38:51+00:00"
    assert emitted["summary"]["run_status"] == "failed"
    assert emitted["summary"]["stage_failure_counts"]["validate"] == 1


def test_run_feature_pipeline_emits_failed_summary_on_ingest_contract_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    emitted: dict[str, object] = {}

    monkeypatch.setattr(
        _orch_feature,
        "get_spots",
        lambda: [{"id": "silvaplana", "shore_orientation_deg": 225}],
    )
    monkeypatch.setattr(
        _orch_feature,
        "fetch_all_spots",
        lambda: (_ for _ in ()).throw(
            ValueError("Unexpected unit for wind_speed_10m: expected km/h, got 'kn'")
        ),
    )
    _capture_emitted_summary(
        monkeypatch,
        "emit_feature_pipeline_run_summary",
        emitted,
        target=_orch_feature,
    )

    with pytest.raises(ValueError, match="Unexpected unit for wind_speed_10m"):
        orchestration.run_feature_pipeline()

    assert emitted["summary"]["run_status"] == "failed"
    assert emitted["summary"]["error"] == (
        "Unexpected unit for wind_speed_10m: expected km/h, got 'kn'"
    )
    assert emitted["summary"]["stage_failure_counts"]["fetch"] == 1
    assert emitted["summary"]["fetched_spot_count"] == 0
    assert emitted["summary"]["spots"] == []


def test_run_feature_pipeline_job_without_mlflow_env_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    clear_tracking_uri_env(monkeypatch)

    def fake_run_feature_pipeline(dataset: str = "train") -> list[str]:
        captured["dataset"] = dataset
        return ["silvaplana"]

    monkeypatch.setattr(
        _orch_feature,
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

    monkeypatch.setenv("MLFLOW_TRACKING_URI", "https://mlflow.example.com")
    monkeypatch.setattr(_orch_feature, "mlflow", _FeatureJobMlflow(logged))
    monkeypatch.setattr(_orch_feature, "configure_mlflow_auth", lambda: None)
    monkeypatch.setattr(
        _orch_feature,
        "get_mlflow_config",
        lambda: {"experiment_name": "foehncast"},
    )
    monkeypatch.setattr(
        _orch_feature,
        "get_storage_config",
        lambda: {"backend": "bigquery"},
    )
    monkeypatch.setattr(
        _orch_feature,
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


def test_run_feature_pipeline_job_context_reports_drift_and_logs_mlflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logged: dict[str, object] = {}

    monkeypatch.setenv("MLFLOW_TRACKING_URI", "https://mlflow.example.com")
    monkeypatch.setattr(_orch_feature, "mlflow", _FeatureJobMlflow(logged))
    monkeypatch.setattr(_orch_feature, "configure_mlflow_auth", lambda: None)
    monkeypatch.setattr(
        _orch_feature,
        "get_mlflow_config",
        lambda: {"experiment_name": "foehncast"},
    )
    monkeypatch.setattr(
        _orch_feature,
        "_run_feature_pipeline_result",
        lambda dataset="train", auto_retraining_mode=None, training_request_stage="Production": {
            "dataset": dataset,
            "storage_backend": "s3",
            "stored_spots": ["silvaplana", "urnersee"],
            "drifted_spots": ["silvaplana"],
            "stage_durations_seconds": {"fetch": 1.5, "store": 2.5},
            "stage_failure_counts": {
                "fetch": 0,
                "engineer": 0,
                "validate": 0,
                "store": 0,
            },
            "dataset_drift_detected": True,
            "feature_persistence_ready": True,
            "training_handoff_ready": True,
            "training_handoff_mode": auto_retraining_mode or "off",
            "training_request_stage": training_request_stage,
        },
    )

    result = orchestration.run_feature_pipeline_job_context(
        dataset="train",
        auto_retraining_mode="drift",
        training_request_stage="Production",
    )

    assert result == {
        "dataset": "train",
        "storage_backend": "s3",
        "stored_spots": ["silvaplana", "urnersee"],
        "drifted_spots": ["silvaplana"],
        "stage_durations_seconds": {"fetch": 1.5, "store": 2.5},
        "stage_failure_counts": {
            "fetch": 0,
            "engineer": 0,
            "validate": 0,
            "store": 0,
        },
        "dataset_drift_detected": True,
        "feature_persistence_ready": True,
        "training_handoff_ready": True,
        "training_handoff_mode": "drift",
        "training_request_stage": "Production",
    }
    assert logged["tracking_uri"] == "https://mlflow.example.com"
    assert logged["experiment_name"] == "foehncast"
    assert logged["run_name"] == "feature-train-refresh"
    assert logged["params"] == {
        "dataset": "train",
        "storage_backend": "s3",
        "stored_spots": "silvaplana,urnersee",
        "drifted_spots": "silvaplana",
        "training_handoff_mode": "drift",
        "training_request_stage": "Production",
    }
    assert logged["metrics"] == {
        "stored_spot_count": 2,
        "drifted_spot_count": 1,
        "fetch_duration_seconds": 1.5,
        "store_duration_seconds": 2.5,
        "fetch_failure_count": 0.0,
        "engineer_failure_count": 0.0,
        "validate_failure_count": 0.0,
        "store_failure_count": 0.0,
        "dataset_drift_detected": 1.0,
        "feature_persistence_ready": 1.0,
        "training_handoff_ready": 1.0,
    }


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        (None, "always"),
        ("always", "always"),
        ("new-data", "always"),
        ("drift", "drift"),
        ("drift-only", "drift"),
        ("off", None),
        ("manual", None),
    ],
)
def test_resolve_auto_retraining_mode_normalizes_values(
    mode: str | None, expected: str | None
) -> None:
    assert (
        orchestration.resolve_auto_retraining_mode(mode, default="always") == expected
    )


def test_resolve_auto_retraining_mode_rejects_unknown_values() -> None:
    with pytest.raises(ValueError, match="Unsupported auto retraining mode"):
        orchestration.resolve_auto_retraining_mode("surprise")


def test_should_auto_retrain_supports_always_and_drift_modes() -> None:
    feature_result = {
        "stored_spots": ["silvaplana"],
        "dataset_drift_detected": False,
    }
    assert orchestration.should_auto_retrain(feature_result, mode="always") is True
    assert orchestration.should_auto_retrain(feature_result, mode="drift") is False

    drift_result = {
        "stored_spots": ["silvaplana"],
        "dataset_drift_detected": True,
    }
    assert orchestration.should_auto_retrain(drift_result, mode="drift") is True


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
    emitted: dict[str, object] = {}

    clear_tracking_uri_env(monkeypatch)

    run = SimpleNamespace(data=SimpleNamespace(metrics={"mae": 0.5}))

    monkeypatch.setattr(_orch_training, "mlflow", _QueriedRunMlflow(run, logged))
    monkeypatch.setattr(
        _orch_training,
        "get_mlflow_tracking_uri",
        lambda: "http://localhost:5001",
    )
    monkeypatch.setattr(
        _orch_training,
        "generate_evaluation_report",
        lambda metrics, output_path: str(tmp_path / "evaluation.md"),
    )
    _capture_emitted_summary(
        monkeypatch,
        "emit_training_pipeline_run_summary",
        emitted,
        target=_orch_training,
    )

    report_path = orchestration.evaluate_training_run("run-123")

    assert report_path == str(tmp_path / "evaluation.md")
    assert logged["tracking_uri"] == "http://localhost:5001"
    assert logged["queried_run_id"] == "run-123"
    assert logged["run_id"] == "run-123"
    assert emitted["summary"]["run_status"] == "running"
    assert emitted["summary"]["evaluation_report_path"] == str(
        tmp_path / "evaluation.md"
    )


def test_evaluate_training_run_uses_matching_history_when_latest_summary_is_other_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    emitted: dict[str, object] = {}
    logged: dict[str, object] = {}
    logged: dict[str, object] = {}

    clear_tracking_uri_env(monkeypatch)

    run = SimpleNamespace(
        data=SimpleNamespace(
            metrics={
                "mae": 0.5,
                "training_input_row_count": 240.0,
                "training_feature_count": 18.0,
                "training_train_row_count": 180.0,
                "training_test_row_count": 60.0,
            }
        )
    )

    monkeypatch.setattr(_orch_training, "mlflow", _QueriedRunMlflow(run, logged))
    monkeypatch.setattr(
        _orch_training,
        "get_mlflow_tracking_uri",
        lambda: "http://localhost:5001",
    )
    monkeypatch.setattr(
        _orch_training,
        "generate_evaluation_report",
        lambda metrics, output_path: str(tmp_path / "evaluation.md"),
    )
    monkeypatch.setattr(
        _orch_training,
        "read_training_pipeline_run_summary",
        lambda dataset="train": {
            "dataset": dataset,
            "requested_stage": "Production",
            "training_run_id": "run-old",
            "stage_durations_seconds": {
                "train": 2.7,
                "evaluate": 0.4,
                "register": 0.3,
            },
            "stage_failure_counts": {"train": 0, "evaluate": 0, "register": 0},
            "training_row_count": 1008,
            "training_feature_count": 14,
            "train_row_count": 806,
            "test_row_count": 202,
            "run_metrics": {"mae": 0.2},
        },
    )
    monkeypatch.setattr(
        _orch_training,
        "read_training_pipeline_run_summary_history",
        lambda dataset=None: [
            {
                "dataset": dataset or "train",
                "requested_stage": "Production",
                "training_run_id": "run-target",
                "stage_durations_seconds": {"train": 1.9},
                "stage_failure_counts": {
                    "train": 0,
                    "evaluate": 0,
                    "register": 0,
                },
                "training_row_count": 240,
                "training_feature_count": 18,
                "train_row_count": 180,
                "test_row_count": 60,
                "run_metrics": {
                    "training_input_row_count": 240.0,
                    "training_feature_count": 18.0,
                    "training_train_row_count": 180.0,
                    "training_test_row_count": 60.0,
                },
            }
        ],
    )
    _capture_emitted_summary(
        monkeypatch,
        "emit_training_pipeline_run_summary",
        emitted,
        target=_orch_training,
    )

    report_path = orchestration.evaluate_training_run(
        "run-target",
        dataset="train",
        requested_stage="Production",
    )

    assert report_path == str(tmp_path / "evaluation.md")
    assert emitted["summary"]["training_run_id"] == "run-target"
    assert emitted["summary"]["training_row_count"] == 240
    assert emitted["summary"]["training_feature_count"] == 18
    assert emitted["summary"]["train_row_count"] == 180
    assert emitted["summary"]["test_row_count"] == 60
    assert emitted["summary"]["stage_states"]["train"] == "succeeded"


def test_training_run_metrics_and_params_normalize_mlflow_run_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logged: dict[str, object] = {}
    run = SimpleNamespace(
        data=SimpleNamespace(
            metrics={"mae": 0.5, "training_input_row_count": 240},
            params={"model_name": "foehncast", "candidate_alias": "candidate"},
        )
    )

    monkeypatch.setattr(_orch_training, "mlflow", _QueriedRunMlflow(run, logged))

    metrics, params = orchestration._training_run_metrics_and_params("run-123")

    assert logged["queried_run_id"] == "run-123"
    assert metrics == {"mae": 0.5, "training_input_row_count": 240.0}
    assert params == {
        "model_name": "foehncast",
        "candidate_alias": "candidate",
    }


def test_register_training_run_registers_and_promotes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logged: dict[str, object] = {}
    emitted: dict[str, object] = {}

    monkeypatch.setattr(
        _orch_training,
        "register_model",
        lambda run_id: SimpleNamespace(version="7"),
    )
    monkeypatch.setattr(
        _orch_training,
        "promote_model",
        lambda model_name, version, stage="Candidate": logged.update(
            {"promotion": (model_name, version, stage)}
        ),
    )
    _capture_emitted_summary(
        monkeypatch,
        "emit_training_pipeline_run_summary",
        emitted,
        target=_orch_training,
    )

    version = orchestration.register_training_run("run-456")

    assert version == "7"
    assert logged["promotion"] == (None, "7", "Candidate")
    assert emitted["summary"]["run_status"] == "succeeded"
    assert emitted["summary"]["registered_model_version"] == "7"


def test_register_training_run_emits_failed_summary_on_registration_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    emitted: dict[str, object] = {}

    def _raise_registration_error(run_id: str) -> SimpleNamespace:
        raise ValueError("registration failed")

    monkeypatch.setattr(_orch_training, "register_model", _raise_registration_error)
    _capture_emitted_summary(
        monkeypatch,
        "emit_training_pipeline_run_summary",
        emitted,
        target=_orch_training,
    )

    with pytest.raises(ValueError, match="registration failed"):
        orchestration.register_training_run("run-456", stage="Production")

    assert emitted["summary"]["run_status"] == "failed"
    assert emitted["summary"]["requested_stage"] == "Production"
    assert emitted["summary"]["training_run_id"] == "run-456"
    assert emitted["summary"]["stage_failure_counts"]["register"] == 1


def test_run_training_pipeline_step_emits_training_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    emitted: dict[str, object] = {}
    logged: dict[str, object] = {}

    run = SimpleNamespace(
        data=SimpleNamespace(
            metrics={
                "mae": 0.5,
                "training_input_row_count": 240.0,
                "training_feature_count": 18.0,
                "training_train_row_count": 180.0,
                "training_test_row_count": 60.0,
            },
            params={"model_name": "foehncast"},
        )
    )

    monkeypatch.setattr(
        _orch_training,
        "run_training_pipeline",
        lambda dataset="train": "run-123",
    )
    monkeypatch.setattr(_orch_training, "mlflow", _QueriedRunMlflow(run, logged))
    _capture_emitted_summary(
        monkeypatch,
        "emit_training_pipeline_run_summary",
        emitted,
        target=_orch_training,
    )

    run_id = orchestration.run_training_pipeline_step(
        dataset="train",
        requested_stage="Production",
    )

    assert run_id == "run-123"
    assert emitted["summary"]["run_status"] == "running"
    assert emitted["summary"]["requested_stage"] == "Production"
    assert emitted["summary"]["training_run_id"] == "run-123"
    assert emitted["summary"]["training_row_count"] == 240


# Drift detection pipeline steps


def test_run_feature_drift_detection_step_checks_all_spots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        _orch_drift,
        "get_spots",
        lambda: [{"id": "bodensee"}, {"id": "silvaplana"}],
    )

    bodensee_df = pd.DataFrame(
        {"wind_speed_10m": [1.0, 2.0, 8.0, 9.0], "temperature_2m": [5, 6, 7, 8]}
    )
    silvaplana_df = pd.DataFrame(
        {"wind_speed_10m": [3.0, 4.0, 10.0, 11.0], "temperature_2m": [9, 10, 11, 12]}
    )

    def fake_read_optional(spot_id: str, dataset: str) -> pd.DataFrame:
        return {"bodensee": bodensee_df, "silvaplana": silvaplana_df}.get(
            spot_id, pd.DataFrame()
        )

    monkeypatch.setattr(_orch_drift, "_read_optional_feature_slice", fake_read_optional)

    emit_calls: list[dict[str, object]] = []

    def fake_emit(*, spot_id: str, dataset: str, reference_df, current_df) -> bool:
        emit_calls.append(
            {
                "spot_id": spot_id,
                "dataset": dataset,
                "ref_rows": len(reference_df),
                "cur_rows": len(current_df),
            }
        )
        return spot_id == "bodensee"

    monkeypatch.setattr(_orch_drift, "_emit_feature_drift_metrics", fake_emit)

    result = orchestration.run_feature_drift_detection_step(dataset="train")

    assert result["dataset"] == "train"
    assert result["checked_spots"] == ["bodensee", "silvaplana"]
    assert result["drifted_spots"] == ["bodensee"]
    assert result["errors"] == {}
    assert len(emit_calls) == 2
    assert emit_calls[0]["spot_id"] == "bodensee"
    assert emit_calls[0]["ref_rows"] == 2
    assert emit_calls[0]["cur_rows"] == 2


def test_run_feature_drift_detection_step_skips_spots_with_insufficient_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        _orch_drift,
        "get_spots",
        lambda: [{"id": "empty_spot"}, {"id": "one_row"}],
    )

    def fake_read_optional(spot_id: str, dataset: str) -> pd.DataFrame:
        if spot_id == "one_row":
            return pd.DataFrame({"wind_speed_10m": [1.0]})
        return pd.DataFrame()

    monkeypatch.setattr(_orch_drift, "_read_optional_feature_slice", fake_read_optional)
    monkeypatch.setattr(
        _orch_drift,
        "_emit_feature_drift_metrics",
        lambda **kw: False,
    )

    result = orchestration.run_feature_drift_detection_step()

    assert result["checked_spots"] == []
    assert result["drifted_spots"] == []
    assert result["errors"] == {}


def test_run_feature_drift_detection_step_captures_per_spot_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        _orch_drift,
        "get_spots",
        lambda: [{"id": "broken"}, {"id": "ok"}],
    )

    def fake_read_optional(spot_id: str, dataset: str) -> pd.DataFrame:
        if spot_id == "broken":
            raise RuntimeError("storage unavailable")
        return pd.DataFrame({"wind_speed_10m": [1.0, 2.0, 3.0, 4.0]})

    monkeypatch.setattr(_orch_drift, "_read_optional_feature_slice", fake_read_optional)
    monkeypatch.setattr(
        _orch_drift,
        "_emit_feature_drift_metrics",
        lambda **kw: False,
    )

    result = orchestration.run_feature_drift_detection_step()

    assert result["checked_spots"] == ["ok"]
    assert "broken" in result["errors"]
    assert "storage unavailable" in result["errors"]["broken"]


def test_run_prediction_drift_detection_step_returns_drift_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from foehncast.monitoring.drift import DriftReport

    fake_report = DriftReport(
        report_kind="prediction",
        dataset_name="inference_predictions",
        dataset_version="v1",
        threshold=0.15,
        reference_row_count=50,
        current_row_count=50,
        column_count=3,
        drifted_column_count=1,
        share_of_drifted_columns=0.33,
        dataset_drift=True,
        generated_at="2026-05-17T00:00:00+00:00",
        metrics=(),
    )

    predictions_df = pd.DataFrame(
        {"prediction": [0.1, 0.2, 0.9, 0.95], "score": [1, 2, 3, 4]}
    )

    monkeypatch.setattr(
        "foehncast.orchestration.drift.push_drift_metrics",
        lambda report: None,
    )
    monkeypatch.setattr(
        "foehncast.monitoring.prediction_log.read_prediction_history",
        lambda path, **kw: predictions_df,
    )
    monkeypatch.setattr(
        "foehncast.monitoring.drift.detect_prediction_drift",
        lambda log: fake_report,
    )

    result = orchestration.run_prediction_drift_detection_step()

    assert result["prediction_drift"] is True
    assert result["drifted_column_count"] == 1
    assert result["column_count"] == 3
    assert result["share_of_drifted_columns"] == 0.33


def test_run_prediction_drift_detection_step_returns_insufficient_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "foehncast.monitoring.prediction_log.read_prediction_history",
        lambda path, **kw: pd.DataFrame(),
    )

    result = orchestration.run_prediction_drift_detection_step()

    assert result["prediction_drift"] is None
    assert result["reason"] == "insufficient_data"


def test_run_prediction_drift_detection_step_handles_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def exploding_read(path, **kw):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(
        "foehncast.monitoring.prediction_log.read_prediction_history",
        exploding_read,
    )

    result = orchestration.run_prediction_drift_detection_step()

    assert result["prediction_drift"] is None
    assert "connection refused" in result["error"]
