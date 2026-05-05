"""Tests for the training pipeline."""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from foehncast.training_pipeline import train


@pytest.fixture()
def feature_columns() -> list[str]:
    return [
        "wind_speed_10m",
        "wind_speed_80m",
        "wind_direction_10m",
        "wind_gusts_10m",
        "temperature_2m",
        "relative_humidity_2m",
        "hour_of_day_sin",
        "hour_of_day_cos",
        "day_of_year_sin",
        "day_of_year_cos",
        "wind_steadiness",
        "gust_factor",
        "shore_alignment",
    ]


@pytest.fixture()
def model_config(feature_columns: list[str]) -> dict[str, object]:
    return {
        "algorithm": "random_forest",
        "features": feature_columns,
        "target": "quality_index",
        "test_size": 0.25,
        "random_state": 42,
    }


@pytest.fixture()
def labeled_training_df(feature_columns: list[str]) -> pd.DataFrame:
    index = pd.date_range("2025-01-01T00:00:00", periods=3, freq="h")
    base_data = {
        "wind_speed_10m": [12.0, 15.0, 18.0],
        "wind_speed_80m": [14.0, 18.0, 20.0],
        "wind_direction_10m": [210.0, 220.0, 230.0],
        "wind_gusts_10m": [18.0, 22.0, 25.0],
        "temperature_2m": [10.0, 11.0, 12.0],
        "relative_humidity_2m": [65.0, 60.0, 55.0],
        "hour_of_day_sin": [0.0, 0.2588190451, 0.5],
        "hour_of_day_cos": [1.0, 0.9659258263, 0.8660254038],
        "day_of_year_sin": [0.0, 0.0, 0.0],
        "day_of_year_cos": [1.0, 1.0, 1.0],
        "wind_steadiness": [0.12, 0.15, 0.10],
        "gust_factor": [1.2, 1.15, 1.1],
        "shore_alignment": [0.7, 0.8, 0.9],
        "quality_index": [2, 3, 4],
    }
    return pd.DataFrame(base_data, index=index)[[*feature_columns, "quality_index"]]


def test_load_training_data_concatenates_spot_frames(
    monkeypatch: pytest.MonkeyPatch,
    model_config: dict[str, object],
    labeled_training_df: pd.DataFrame,
) -> None:
    monkeypatch.setattr(train, "get_model_config", lambda: model_config)
    monkeypatch.setattr(train, "get_rider_config", lambda: {"weight_kg": 80})
    monkeypatch.setattr(
        train,
        "get_spots",
        lambda: [{"id": "silvaplana"}, {"id": "urnersee"}],
    )
    monkeypatch.setattr(
        train,
        "read_features",
        lambda spot_id, dataset: labeled_training_df.drop(columns=["quality_index"]),
    )
    monkeypatch.setattr(
        train,
        "label_dataset",
        lambda features_df, rider_config: labeled_training_df.copy(),
    )

    features_df, target_series = train.load_training_data()

    assert len(features_df) == 6
    assert len(target_series) == 6
    assert list(features_df.columns) == model_config["features"]
    assert target_series.name == model_config["target"]


def test_load_training_data_adds_time_features_before_labeling(
    monkeypatch: pytest.MonkeyPatch,
    model_config: dict[str, object],
    labeled_training_df: pd.DataFrame,
) -> None:
    logged: dict[str, object] = {}
    stored_feature_df = labeled_training_df.drop(
        columns=[
            "quality_index",
            "hour_of_day_sin",
            "hour_of_day_cos",
            "day_of_year_sin",
            "day_of_year_cos",
        ]
    )

    monkeypatch.setattr(train, "get_model_config", lambda: model_config)
    monkeypatch.setattr(train, "get_rider_config", lambda: {"weight_kg": 80})
    monkeypatch.setattr(train, "get_spots", lambda: [{"id": "silvaplana"}])
    monkeypatch.setattr(
        train, "read_features", lambda spot_id, dataset: stored_feature_df
    )

    def _label_dataset(
        features_df: pd.DataFrame, rider_config: dict[str, object]
    ) -> pd.DataFrame:
        logged["columns_before_labeling"] = list(features_df.columns)
        labeled = features_df.copy()
        labeled["quality_index"] = [2, 3, 4]
        return labeled

    monkeypatch.setattr(train, "label_dataset", _label_dataset)

    features_df, _ = train.load_training_data()

    assert "hour_of_day_sin" in logged["columns_before_labeling"]
    assert "hour_of_day_cos" in logged["columns_before_labeling"]
    assert "day_of_year_sin" in logged["columns_before_labeling"]
    assert "day_of_year_cos" in logged["columns_before_labeling"]
    assert list(features_df.columns) == model_config["features"]


def test_load_training_data_raises_when_no_data_is_available(
    monkeypatch: pytest.MonkeyPatch, model_config: dict[str, object]
) -> None:
    monkeypatch.setattr(train, "get_model_config", lambda: model_config)
    monkeypatch.setattr(train, "get_rider_config", lambda: {"weight_kg": 80})
    monkeypatch.setattr(train, "get_spots", lambda: [{"id": "silvaplana"}])

    def _missing_features(spot_id: str, dataset: str) -> pd.DataFrame:
        raise FileNotFoundError

    monkeypatch.setattr(train, "read_features", _missing_features)

    with pytest.raises(ValueError, match="No training data available"):
        train.load_training_data()


def test_train_model_returns_random_forest_estimator(
    model_config: dict[str, object], labeled_training_df: pd.DataFrame
) -> None:
    model = train.train_model(
        labeled_training_df[model_config["features"]],
        labeled_training_df[model_config["target"]],
        model_config,
    )

    assert model.__class__.__name__ == "RandomForestRegressor"


def test_train_model_rejects_unsupported_algorithm(
    labeled_training_df: pd.DataFrame, model_config: dict[str, object]
) -> None:
    invalid_config = {**model_config, "algorithm": "linear_regression"}

    with pytest.raises(ValueError, match="Unsupported model algorithm"):
        train.train_model(
            labeled_training_df[model_config["features"]],
            labeled_training_df[model_config["target"]],
            invalid_config,
        )


def test_run_training_pipeline_logs_mlflow_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    model_config: dict[str, object],
    labeled_training_df: pd.DataFrame,
) -> None:
    logged: dict[str, object] = {}

    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)

    class FakeRun:
        def __init__(self) -> None:
            self.info = SimpleNamespace(run_id="run-123")

        def __enter__(self) -> FakeRun:
            return self

        def __exit__(self, exc_type, exc, exc_tb) -> None:
            return None

    class FakeModel:
        feature_importances_ = [
            0.20,
            0.14,
            0.11,
            0.10,
            0.09,
            0.08,
            0.07,
            0.06,
            0.05,
            0.04,
            0.03,
            0.02,
            0.01,
        ]

        def predict(self, features_df: pd.DataFrame) -> list[float]:
            return [2.5 for _ in range(len(features_df))]

    class FakeMlflow:
        def __init__(self) -> None:
            self.sklearn = SimpleNamespace(
                log_model=lambda model, artifact_path: logged.update(
                    {
                        "logged_model": model,
                        "artifact_path": artifact_path,
                    }
                )
            )

        def set_tracking_uri(self, tracking_uri: str) -> None:
            logged["tracking_uri"] = tracking_uri

        def set_experiment(self, experiment_name: str) -> None:
            logged["experiment_name"] = experiment_name

        def start_run(self, run_name: str) -> FakeRun:
            logged["run_name"] = run_name
            return FakeRun()

        def log_params(self, params: dict[str, object]) -> None:
            logged["params"] = params

        def log_metrics(self, metrics: dict[str, float]) -> None:
            logged["metrics"] = metrics

        def log_artifact(self, path: str, artifact_path: str | None = None) -> None:
            logged["artifact"] = (path, artifact_path)

    monkeypatch.setattr(train, "mlflow", FakeMlflow())
    monkeypatch.setattr(
        train,
        "get_mlflow_config",
        lambda: {"tracking_uri": "http://mlflow", "experiment_name": "foehncast"},
    )
    monkeypatch.setattr(train, "get_mlflow_tracking_uri", lambda: "http://mlflow")
    monkeypatch.setattr(
        train,
        "load_training_data",
        lambda: (
            labeled_training_df[model_config["features"]],
            labeled_training_df[model_config["target"]],
        ),
    )
    monkeypatch.setattr(
        train,
        "train_test_split",
        lambda features_df, target_series, test_size, random_state: (
            features_df.iloc[:1],
            features_df.iloc[1:],
            target_series.iloc[:1],
            target_series.iloc[1:],
        ),
    )
    monkeypatch.setattr(
        train, "train_model", lambda features_df, target_series, cfg: FakeModel()
    )
    monkeypatch.setattr(
        train,
        "_log_feature_importance_plot",
        lambda model, feature_columns: logged.update(
            {"feature_plot": list(feature_columns)}
        ),
    )

    run_id = train.run_training_pipeline(model_config)

    assert run_id == "run-123"
    assert logged["tracking_uri"] == "http://mlflow"
    assert logged["experiment_name"] == "foehncast"
    assert logged["run_name"] == "random_forest-train"
    assert logged["params"]["algorithm"] == "random_forest"
    assert set(logged["metrics"].keys()) >= {
        "mae",
        "rmse",
        "r2",
        "overall_class_accuracy",
    }
    assert logged["artifact_path"] == "model"
    assert logged["feature_plot"] == model_config["features"]
