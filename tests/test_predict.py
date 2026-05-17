"""Tests for prediction helpers and serving endpoints."""

from __future__ import annotations

from dataclasses import asdict
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi import BackgroundTasks
from fastapi.testclient import TestClient
from prometheus_client import CONTENT_TYPE_LATEST

from foehncast.inference_pipeline import predict, serve
from foehncast.inference_pipeline.rank import RankedSpot
from tests.mlflow_fixtures import clear_tracking_uri_env


@pytest.fixture()
def model_config() -> dict[str, object]:
    return {
        "features": [
            "wind_speed_10m",
            "wind_gusts_10m",
            "hour_of_day_sin",
            "hour_of_day_cos",
            "day_of_year_sin",
            "day_of_year_cos",
            "wind_direction_10m_sin",
            "wind_direction_10m_cos",
            "wind_steadiness",
            "gust_excess_10m",
            "shore_alignment",
        ]
    }


@pytest.fixture()
def spot() -> dict[str, object]:
    return {
        "id": "silvaplana",
        "name": "Silvaplana",
        "lat": 46.45,
        "lon": 9.79,
        "shore_orientation_deg": 225,
    }


@pytest.fixture()
def forecast_df() -> pd.DataFrame:
    index = pd.date_range("2025-01-01T00:00:00", periods=3, freq="h")
    return pd.DataFrame(
        {
            "wind_speed_10m": [14.0, 16.0, 18.0],
            "wind_gusts_10m": [18.0, 20.0, 22.0],
            "wind_direction_10m": [210.0, 220.0, 230.0],
        },
        index=index,
    )


class _AliasLookupClient:
    def __init__(self, logged: dict[str, object], version: str) -> None:
        self._logged = logged
        self._version = version

    def get_model_version_by_alias(self, model_name: str, alias: str) -> object:
        self._logged["lookup"] = (model_name, alias)
        return SimpleNamespace(version=self._version)


class _AliasLookupMlflow:
    def __init__(self, logged: dict[str, object], version: str) -> None:
        self._logged = logged
        self._version = version

    def set_tracking_uri(self, tracking_uri: str) -> None:
        self._logged["tracking_uri"] = tracking_uri

    def MlflowClient(self) -> _AliasLookupClient:
        return _AliasLookupClient(self._logged, self._version)


def _patch_serving_model_version_lookup(
    monkeypatch: pytest.MonkeyPatch,
    logged: dict[str, object],
    version: str,
) -> None:
    monkeypatch.setattr(predict, "mlflow", _AliasLookupMlflow(logged, version))
    monkeypatch.setattr(
        predict,
        "get_mlflow_config",
        lambda: {
            "tracking_uri": "http://localhost:5001",
            "model_name": "foehncast-quality",
            "candidate_alias": "candidate",
            "champion_alias": "champion",
        },
    )
    monkeypatch.setattr(
        predict,
        "get_mlflow_tracking_uri",
        lambda: "http://localhost:5001",
    )


def test_get_serving_model_version_reads_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logged: dict[str, object] = {}

    monkeypatch.delenv("FOEHNCAST_MLFLOW_SERVING_ALIAS", raising=False)
    clear_tracking_uri_env(monkeypatch)
    _patch_serving_model_version_lookup(monkeypatch, logged, "5")

    model_version = predict.get_serving_model_version()

    assert model_version == "5"
    assert logged["tracking_uri"] == "http://localhost:5001"
    assert logged["lookup"] == ("foehncast-quality", "champion")


def test_get_serving_model_version_prefers_env_alias_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logged: dict[str, object] = {}

    monkeypatch.setenv("FOEHNCAST_MLFLOW_SERVING_ALIAS", "candidate")
    clear_tracking_uri_env(monkeypatch)
    _patch_serving_model_version_lookup(monkeypatch, logged, "11")

    model_version = predict.get_serving_model_version()

    assert model_version == "11"
    assert logged["tracking_uri"] == "http://localhost:5001"
    assert logged["lookup"] == ("foehncast-quality", "candidate")


def test_predict_spots_returns_forecasts_for_requested_spots(
    monkeypatch: pytest.MonkeyPatch,
    model_config: dict[str, object],
    spot: dict[str, object],
    forecast_df: pd.DataFrame,
) -> None:
    class FakeModel:
        def predict(self, features_df: pd.DataFrame) -> list[float]:
            assert list(features_df.columns) == model_config["features"]
            return [2.1, 3.2]

    monkeypatch.setattr(predict, "get_serving_model_alias", lambda: "champion")
    monkeypatch.setattr(
        predict,
        "get_model_by_alias",
        lambda alias: FakeModel() if alias == "champion" else None,
    )
    monkeypatch.setattr(predict, "get_model_config", lambda: model_config)
    monkeypatch.setattr(
        predict, "get_inference_config", lambda: {"max_horizon_hours": 2}
    )
    monkeypatch.setattr(predict, "get_spots", lambda: [spot])
    monkeypatch.setattr(predict, "fetch_forecast", lambda lat, lon: forecast_df)
    monkeypatch.setattr(
        predict,
        "get_serving_model_version",
        lambda model_name=None, alias=None: "7",
    )

    result = predict.predict_spots(["silvaplana"])

    assert result["model_version"] == "7"
    assert len(result["predictions"]) == 1
    assert result["predictions"][0]["spot_id"] == "silvaplana"
    assert result["predictions"][0]["spot_name"] == "Silvaplana"
    assert len(result["predictions"][0]["forecast"]) == 2
    assert result["predictions"][0]["forecast"][0]["quality_index"] == 2.1


def test_predict_spots_rejects_unknown_spots(
    monkeypatch: pytest.MonkeyPatch, spot: dict[str, object]
) -> None:
    monkeypatch.setattr(predict, "get_spots", lambda: [spot])

    with pytest.raises(KeyError, match="Unknown spot requested"):
        predict.predict_spots(["unknown-spot"])


def test_health_endpoint_reports_model_version(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(serve, "get_serving_model_version", lambda: "9")
    monkeypatch.setattr(serve, "get_serving_model_alias", lambda: "candidate")
    client = TestClient(serve.app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "model_alias": "candidate",
        "model_version": "9",
    }


def test_spots_endpoint_lists_available_spots(
    monkeypatch: pytest.MonkeyPatch, spot: dict[str, object]
) -> None:
    monkeypatch.setattr(serve, "list_available_spots", lambda: [spot])
    client = TestClient(serve.app)

    response = client.get("/spots")

    assert response.status_code == 200
    assert response.json() == [spot]


def test_schedule_prediction_monitoring_enqueues_background_task() -> None:
    payload = {"model_version": "11", "predictions": []}
    background_tasks = BackgroundTasks()

    serve._schedule_prediction_monitoring(
        background_tasks,
        payload,
        endpoint="predict",
        spot_ids=["silvaplana"],
    )

    assert len(background_tasks.tasks) == 1
    task = background_tasks.tasks[0]
    assert task.func is serve._emit_prediction_monitoring
    assert task.args == (payload,)
    assert task.kwargs == {
        "endpoint": "predict",
        "spot_ids": ["silvaplana"],
    }


def test_schedule_prediction_monitoring_ignores_background_task_failure() -> None:
    class BrokenBackgroundTasks:
        def add_task(self, *args: object, **kwargs: object) -> None:
            raise RuntimeError("background queue unavailable")

    serve._schedule_prediction_monitoring(
        BrokenBackgroundTasks(),
        {"model_version": "11", "predictions": []},
        endpoint="predict",
        spot_ids=["silvaplana"],
    )


def test_predict_endpoint_returns_prediction_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "model_version": "11",
        "predictions": [
            {
                "spot_id": "silvaplana",
                "spot_name": "Silvaplana",
                "forecast": [{"time": "2025-01-01T00:00:00", "quality_index": 2.4}],
            }
        ],
    }
    monkeypatch.setattr(serve, "predict_spots", lambda spot_ids: payload)
    recorded: dict[str, object] = {}
    monkeypatch.setattr(
        serve,
        "emit_prediction_drift_metrics",
        lambda prediction_payload, endpoint, spot_ids=None: recorded.update(
            {
                "prediction_payload": prediction_payload,
                "endpoint": endpoint,
                "spot_ids": spot_ids,
            }
        ),
    )
    client = TestClient(serve.app)

    response = client.post("/predict", json={"spot_ids": ["silvaplana"]})

    assert response.status_code == 200
    assert response.json() == payload
    assert recorded == {
        "prediction_payload": payload,
        "endpoint": "predict",
        "spot_ids": ["silvaplana"],
    }


def test_predict_endpoint_returns_404_for_unknown_spot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_missing_spot(spot_ids: list[str] | None) -> dict[str, object]:
        raise KeyError("Unknown spot requested: unknown-spot")

    monkeypatch.setattr(serve, "predict_spots", raise_missing_spot)
    client = TestClient(serve.app)

    response = client.post("/predict", json={"spot_ids": ["unknown-spot"]})

    assert response.status_code == 404
    assert response.json() == {"detail": "Unknown spot requested: unknown-spot"}


def test_rank_endpoint_returns_ranked_spots_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "model_version": "11",
        "predictions": [
            {
                "spot_id": "silvaplana",
                "spot_name": "Silvaplana",
                "forecast": [{"time": "2025-01-01T00:00:00", "quality_index": 3.4}],
            }
        ],
    }
    ranked_spots = [
        RankedSpot(
            spot_id="silvaplana",
            spot_name="Silvaplana",
            quality_index=3.4,
            drive_minutes=95.0,
            session_hours=3.0,
            ride_drive_ratio=6.442105263157894,
            score=1.0,
        )
    ]

    monkeypatch.setattr(serve, "predict_spots", lambda spot_ids: payload)
    recorded: dict[str, object] = {}
    monkeypatch.setattr(
        serve,
        "emit_prediction_drift_metrics",
        lambda prediction_payload, endpoint, spot_ids=None: recorded.update(
            {
                "prediction_payload": prediction_payload,
                "endpoint": endpoint,
                "spot_ids": spot_ids,
            }
        ),
    )
    monkeypatch.setattr(
        serve,
        "get_rider_config",
        lambda: {"home_lat": 47.02, "home_lon": 8.65},
    )
    monkeypatch.setattr(
        serve, "rank_spots", lambda predictions, rider_config: ranked_spots
    )
    client = TestClient(serve.app)

    response = client.post("/rank", json={"spot_ids": ["silvaplana"]})

    assert response.status_code == 200
    assert response.json() == {
        "model_version": "11",
        "ranked_spots": [asdict(ranked_spots[0])],
    }
    assert recorded == {
        "prediction_payload": payload,
        "endpoint": "rank",
        "spot_ids": ["silvaplana"],
    }


def test_predict_endpoint_ignores_prediction_monitoring_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {"model_version": "11", "predictions": []}
    monkeypatch.setattr(serve, "predict_spots", lambda spot_ids: payload)
    monkeypatch.setattr(
        serve,
        "emit_prediction_drift_metrics",
        lambda prediction_payload, endpoint, spot_ids=None: (_ for _ in ()).throw(
            RuntimeError("statsd unavailable")
        ),
    )
    client = TestClient(serve.app)

    response = client.post("/predict", json={"spot_ids": ["silvaplana"]})

    assert response.status_code == 200
    assert response.json() == payload


def test_rank_endpoint_returns_404_for_unknown_spot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_missing_spot(spot_ids: list[str] | None) -> dict[str, object]:
        raise KeyError("Unknown spot requested: unknown-spot")

    monkeypatch.setattr(serve, "predict_spots", raise_missing_spot)
    client = TestClient(serve.app)

    response = client.post("/rank", json={"spot_ids": ["unknown-spot"]})

    assert response.status_code == 404
    assert response.json() == {"detail": "Unknown spot requested: unknown-spot"}


def test_online_features_endpoint_returns_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "feature_service": None,
        "returned_features": ["wind_speed_10m", "gust_excess_10m"],
        "rows": [
            {
                "spot_id": "silvaplana",
                "wind_speed_10m": 14.0,
                "gust_excess_10m": 4.0,
            }
        ],
    }
    monkeypatch.setattr(
        serve,
        "get_online_spot_features",
        lambda spot_ids, feature_names: payload,
    )
    client = TestClient(serve.app)

    response = client.post(
        "/features/online",
        json={
            "spot_ids": ["silvaplana"],
            "feature_names": ["wind_speed_10m", "gust_excess_10m"],
        },
    )

    assert response.status_code == 200
    assert response.json() == payload


def test_online_features_endpoint_returns_404_for_unknown_spot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_missing_spot(
        spot_ids: list[str] | None, feature_names: list[str] | None
    ) -> dict[str, object]:
        raise KeyError("Unknown spot requested: unknown-spot")

    monkeypatch.setattr(serve, "get_online_spot_features", raise_missing_spot)
    client = TestClient(serve.app)

    response = client.post(
        "/features/online",
        json={"spot_ids": ["unknown-spot"], "feature_names": ["wind_speed_10m"]},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Unknown spot requested: unknown-spot"}


def test_online_features_endpoint_returns_400_for_invalid_features(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_invalid_features(
        spot_ids: list[str] | None, feature_names: list[str] | None
    ) -> dict[str, object]:
        raise ValueError("At least one non-empty feature name must be provided")

    monkeypatch.setattr(serve, "get_online_spot_features", raise_invalid_features)
    client = TestClient(serve.app)

    response = client.post(
        "/features/online",
        json={"spot_ids": ["silvaplana"], "feature_names": [""]},
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "At least one non-empty feature name must be provided"
    }


def test_online_features_endpoint_returns_503_when_feast_runtime_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_unavailable(
        spot_ids: list[str] | None, feature_names: list[str] | None
    ) -> dict[str, object]:
        raise RuntimeError("Feast runtime is unavailable")

    monkeypatch.setattr(serve, "get_online_spot_features", raise_unavailable)
    client = TestClient(serve.app)

    response = client.post(
        "/features/online",
        json={"spot_ids": ["silvaplana"], "feature_names": ["wind_speed_10m"]},
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "Feast runtime is unavailable"}


def test_online_features_demo_endpoint_returns_html(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        serve,
        "render_online_features_demo",
        lambda: "<html><body>online features demo</body></html>",
    )
    client = TestClient(serve.app)

    response = client.get("/features/online/demo")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert response.text == "<html><body>online features demo</body></html>"


def test_metrics_endpoint_returns_prometheus_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    feature_payload = (
        b"# HELP foehncast_feature_pipeline_summary_count example\n"
        b"foehncast_feature_pipeline_summary_count 1\n"
    )
    training_payload = (
        b"# HELP foehncast_training_pipeline_summary_count example\n"
        b"foehncast_training_pipeline_summary_count 1\n"
    )
    prediction_payload = (
        b"# HELP foehncast_prediction_log_total_row_count example\n"
        b"foehncast_prediction_log_total_row_count 2\n"
    )
    monitoring_payload = (
        b"# HELP foehncast_prediction_monitoring_schedule_total example\n"
        b'foehncast_prediction_monitoring_schedule_total{endpoint="predict",result="scheduled"} 1\n'
    )
    hosted_sync_payload = (
        b"# HELP foehncast_online_compose_sync_status_file_present example\n"
        b"foehncast_online_compose_sync_status_file_present 1\n"
    )
    monkeypatch.setattr(
        serve,
        "render_feature_pipeline_prometheus_metrics",
        lambda: feature_payload,
    )
    monkeypatch.setattr(
        serve,
        "render_training_pipeline_prometheus_metrics",
        lambda: training_payload,
    )
    monkeypatch.setattr(
        serve,
        "render_prediction_log_prometheus_metrics",
        lambda: prediction_payload,
    )
    monkeypatch.setattr(
        serve,
        "render_prediction_monitoring_prometheus_metrics",
        lambda: monitoring_payload,
    )
    monkeypatch.setattr(
        serve,
        "render_hosted_sync_prometheus_metrics",
        lambda: hosted_sync_payload,
    )
    hindcast_payload = (
        b"# HELP foehncast_hindcast_accuracy example\nfoehncast_hindcast_accuracy 0.5\n"
    )
    monkeypatch.setattr(
        serve,
        "render_hindcast_prometheus_metrics",
        lambda: hindcast_payload,
    )
    monkeypatch.setattr(
        serve,
        "render_inference_prometheus_metrics",
        lambda: b"",
    )
    client = TestClient(serve.app)

    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.content == (
        feature_payload
        + training_payload
        + prediction_payload
        + hosted_sync_payload
        + hindcast_payload
        + monitoring_payload
    )
    assert response.headers["content-type"] == CONTENT_TYPE_LATEST
