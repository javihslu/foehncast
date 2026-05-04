"""Tests for model evaluation helpers."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from foehncast.training_pipeline import evaluate


class ConstantModel:
    def __init__(self, predictions: list[float]) -> None:
        self._predictions = predictions

    def predict(self, features_test: pd.DataFrame) -> list[float]:
        return self._predictions


def test_evaluate_model_returns_regression_and_class_metrics() -> None:
    features_test = pd.DataFrame({"wind_speed_10m": [10.0, 20.0, 30.0]})
    target_test = pd.Series([1, 3, 4])
    model = ConstantModel([1.2, 2.8, 3.6])

    metrics = evaluate.evaluate_model(model, features_test, target_test)

    assert set(metrics) >= {
        "mae",
        "rmse",
        "r2",
        "overall_class_accuracy",
        "class_accuracy_1",
        "class_accuracy_3",
        "class_accuracy_4",
    }
    assert metrics["overall_class_accuracy"] == 1.0


def test_evaluate_model_logs_metrics_when_mlflow_run_is_active(monkeypatch) -> None:
    logged: dict[str, dict[str, float]] = {}

    class FakeMlflow:
        def active_run(self) -> object:
            return object()

        def log_metrics(self, metrics: dict[str, float]) -> None:
            logged["metrics"] = metrics

    monkeypatch.setattr(evaluate, "mlflow", FakeMlflow())

    features_test = pd.DataFrame({"wind_speed_10m": [10.0, 20.0]})
    target_test = pd.Series([1, 2])
    model = ConstantModel([1.0, 2.0])

    metrics = evaluate.evaluate_model(model, features_test, target_test)

    assert logged["metrics"] == metrics


def test_generate_evaluation_report_writes_markdown(tmp_path: Path) -> None:
    metrics = {"mae": 0.5, "rmse": 0.75, "r2": 0.8}

    report_path = evaluate.generate_evaluation_report(
        metrics, str(tmp_path / "reports" / "evaluation.md")
    )

    content = Path(report_path).read_text()
    assert "# Evaluation Report" in content
    assert "| mae | 0.5000 |" in content
    assert Path(report_path).exists()


def test_generate_evaluation_report_logs_artifact_when_mlflow_run_is_active(
    monkeypatch, tmp_path: Path
) -> None:
    logged: dict[str, tuple[str, str | None]] = {}

    class FakeMlflow:
        def active_run(self) -> object:
            return object()

        def log_artifact(self, path: str, artifact_path: str | None = None) -> None:
            logged["artifact"] = (path, artifact_path)

    monkeypatch.setattr(evaluate, "mlflow", FakeMlflow())

    report_path = evaluate.generate_evaluation_report(
        {"mae": 0.5}, str(tmp_path / "evaluation.md")
    )

    assert logged["artifact"] == (report_path, "evaluation")


def test_compare_models_returns_metrics_dataframe(monkeypatch) -> None:
    run_lookup = {
        "run-1": SimpleNamespace(
            data=SimpleNamespace(
                params={"algorithm": "random_forest"},
                metrics={"mae": 0.4, "rmse": 0.6, "r2": 0.8},
            )
        ),
        "run-2": SimpleNamespace(
            data=SimpleNamespace(
                params={"algorithm": "gradient_boosting"},
                metrics={"mae": 0.5, "rmse": 0.7, "r2": 0.7},
            )
        ),
    }
    logged: dict[str, str] = {}

    class FakeClient:
        def get_run(self, run_id: str):
            return run_lookup[run_id]

    class FakeMlflow:
        def set_tracking_uri(self, tracking_uri: str) -> None:
            logged["tracking_uri"] = tracking_uri

        def MlflowClient(self) -> FakeClient:
            return FakeClient()

    monkeypatch.setattr(evaluate, "mlflow", FakeMlflow())
    monkeypatch.setattr(
        evaluate,
        "get_mlflow_config",
        lambda: {"tracking_uri": "http://localhost:5001"},
    )

    result = evaluate.compare_models(["run-1", "run-2"])

    assert logged["tracking_uri"] == "http://localhost:5001"
    assert list(result["run_id"]) == ["run-1", "run-2"]
    assert list(result["algorithm"]) == ["random_forest", "gradient_boosting"]
    assert list(result["mae"]) == [0.4, 0.5]
