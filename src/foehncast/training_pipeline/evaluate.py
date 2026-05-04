"""Model evaluation metrics and reporting."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import mlflow
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from foehncast.config import get_mlflow_config


def _rounded_predictions(predictions: Any, target_true: pd.Series) -> pd.Series:
    lower = int(target_true.min())
    upper = int(target_true.max())
    rounded = pd.Series(predictions, index=target_true.index).round().clip(lower, upper)
    return rounded.astype(int)


def _class_accuracy_metrics(
    target_true: pd.Series, predictions: Any
) -> dict[str, float]:
    rounded_predictions = _rounded_predictions(predictions, target_true)
    metrics = {
        "overall_class_accuracy": float((rounded_predictions == target_true).mean())
    }

    for label in sorted(target_true.astype(int).unique()):
        mask = target_true == label
        metrics[f"class_accuracy_{label}"] = float(
            (rounded_predictions[mask] == target_true[mask]).mean()
        )

    return metrics


def evaluate_model(
    model: Any, features_test: pd.DataFrame, target_test: pd.Series
) -> dict[str, float]:
    """Compute regression and class-bucket metrics for a trained model."""
    predictions = model.predict(features_test)
    metrics = {
        "mae": float(mean_absolute_error(target_test, predictions)),
        "rmse": float(mean_squared_error(target_test, predictions) ** 0.5),
        "r2": float(r2_score(target_test, predictions)),
    }
    metrics.update(_class_accuracy_metrics(target_test, predictions))

    active_run = getattr(mlflow, "active_run", lambda: None)()
    if active_run is not None:
        mlflow.log_metrics(metrics)

    return metrics


def generate_evaluation_report(metrics: dict[str, float], output_path: str) -> str:
    """Write a markdown evaluation report and return its path."""
    report_path = Path(output_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    lines = ["# Evaluation Report", "", "| Metric | Value |", "| --- | ---: |"]
    for name, value in metrics.items():
        lines.append(f"| {name} | {value:.4f} |")
    report_path.write_text("\n".join(lines) + "\n")

    active_run = getattr(mlflow, "active_run", lambda: None)()
    if active_run is not None:
        mlflow.log_artifact(str(report_path), artifact_path="evaluation")

    return str(report_path)


def compare_models(run_ids: list[str]) -> pd.DataFrame:
    """Compare MLflow runs by collecting their logged metrics into a dataframe."""
    mlflow_config = get_mlflow_config()
    mlflow.set_tracking_uri(mlflow_config["tracking_uri"])
    client = mlflow.MlflowClient()
    rows: list[dict[str, Any]] = []

    for run_id in run_ids:
        run = client.get_run(run_id)
        row: dict[str, Any] = {
            "run_id": run_id,
            "algorithm": run.data.params.get("algorithm"),
        }
        row.update(run.data.metrics)
        rows.append(row)

    return pd.DataFrame(rows)
