"""Model training with scikit-learn."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import mlflow
import mlflow.sklearn
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.model_selection import train_test_split

from foehncast.config import (
    get_mlflow_config,
    get_model_config,
    get_rider_config,
    get_spots,
)
from foehncast.feature_pipeline.engineer import add_time_features
from foehncast.feature_pipeline.store import read_features
from foehncast.training_pipeline.evaluate import compute_metrics
from foehncast.training_pipeline.label import label_dataset


def load_training_data(dataset: str = "train") -> tuple[pd.DataFrame, pd.Series]:
    """Load all available stored feature data and return model inputs and target."""
    model_config = get_model_config()
    rider_config = get_rider_config()
    labeled_frames: list[pd.DataFrame] = []

    for spot in get_spots():
        spot_id = spot["id"]
        try:
            features_df = read_features(spot_id=spot_id, dataset=dataset)
        except FileNotFoundError:
            continue

        if features_df.empty:
            continue

        # Rebuild time features here so training still works with older stored
        # datasets after the feature schema grows.
        features_df = add_time_features(features_df)
        labeled_frames.append(label_dataset(features_df, rider_config))

    if not labeled_frames:
        raise ValueError(f"No training data available for dataset '{dataset}'")

    training_df = pd.concat(labeled_frames, ignore_index=True)
    feature_columns = model_config["features"]
    target_column = model_config["target"]
    missing_columns = sorted(
        set([*feature_columns, target_column]) - set(training_df.columns)
    )
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise KeyError(f"Training data is missing required columns: {missing}")

    return training_df[feature_columns].copy(), training_df[target_column].copy()


def _build_model(model_config: dict[str, Any]) -> Any:
    algorithm = model_config["algorithm"]
    random_state = model_config["random_state"]

    if algorithm == "random_forest":
        return RandomForestRegressor(n_estimators=200, random_state=random_state)
    if algorithm == "gradient_boosting":
        return GradientBoostingRegressor(random_state=random_state)

    raise ValueError(f"Unsupported model algorithm: {algorithm}")


def train_model(
    features_df: pd.DataFrame, target_series: pd.Series, model_config: dict[str, Any]
) -> Any:
    """Fit the configured regression model and return the trained estimator."""
    model = _build_model(model_config)
    model.fit(features_df, target_series)
    return model


def _tracking_uri(mlflow_config: dict[str, Any]) -> str:
    return os.getenv("MLFLOW_TRACKING_URI", mlflow_config["tracking_uri"])


def _log_feature_importance_plot(model: Any, feature_columns: list[str]) -> None:
    if not hasattr(model, "feature_importances_"):
        return

    importance_df = pd.DataFrame(
        {"feature": feature_columns, "importance": model.feature_importances_}
    ).sort_values("importance", ascending=True)

    figure, axis = plt.subplots(figsize=(8, 4.5))
    axis.barh(importance_df["feature"], importance_df["importance"])
    axis.set_xlabel("Importance")
    axis.set_ylabel("Feature")
    axis.set_title("Feature importance")
    figure.tight_layout()

    with tempfile.TemporaryDirectory() as tmpdir:
        plot_path = Path(tmpdir) / "feature_importance.png"
        figure.savefig(plot_path)
        mlflow.log_artifact(str(plot_path), artifact_path="plots")

    plt.close(figure)


def run_training_pipeline(model_config: dict[str, Any] | None = None) -> str:
    """Train the configured model, log the run to MLflow, and return the run id."""
    resolved_model_config = model_config or get_model_config()
    mlflow_config = get_mlflow_config()
    mlflow.set_tracking_uri(_tracking_uri(mlflow_config))
    mlflow.set_experiment(mlflow_config["experiment_name"])

    features_df, target_series = load_training_data()
    (
        features_train,
        features_test,
        target_train,
        target_test,
    ) = train_test_split(
        features_df,
        target_series,
        test_size=resolved_model_config["test_size"],
        random_state=resolved_model_config["random_state"],
    )
    model = train_model(features_train, target_train, resolved_model_config)
    target_pred = model.predict(features_test)
    metrics = compute_metrics(target_test, target_pred)

    with mlflow.start_run(
        run_name=f"{resolved_model_config['algorithm']}-train"
    ) as run:
        mlflow.log_params(
            {
                "algorithm": resolved_model_config["algorithm"],
                "test_size": resolved_model_config["test_size"],
                "random_state": resolved_model_config["random_state"],
                "features": ",".join(resolved_model_config["features"]),
            }
        )
        mlflow.log_metrics(metrics)
        mlflow.sklearn.log_model(model, artifact_path="model")
        _log_feature_importance_plot(model, resolved_model_config["features"])
        return run.info.run_id
