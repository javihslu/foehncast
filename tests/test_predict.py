"""Tests for prediction helpers and serving endpoints."""

from __future__ import annotations

from dataclasses import asdict
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from foehncast.inference_pipeline import predict, serve
from foehncast.inference_pipeline.rank import RankedSpot


@pytest.fixture()
def model_config() -> dict[str, object]:
    return {
        "features": [
            "wind_speed_10m",
            "wind_gusts_10m",
            "wind_direction_10m",
            "hour_of_day_sin",
            "hour_of_day_cos",
            "day_of_year_sin",
            "day_of_year_cos",
            "wind_steadiness",
            "gust_factor",
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


def test_get_serving_model_version_reads_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logged: dict[str, object] = {}

    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)

    class FakeClient:
        def get_model_version_by_alias(self, model_name: str, alias: str) -> object:
            logged["lookup"] = (model_name, alias)
            return SimpleNamespace(version="5")

    class FakeMlflow:
        def set_tracking_uri(self, tracking_uri: str) -> None:
            logged["tracking_uri"] = tracking_uri

        def MlflowClient(self) -> FakeClient:
            return FakeClient()

    monkeypatch.setattr(predict, "mlflow", FakeMlflow())
    monkeypatch.setattr(
        predict,
        "get_mlflow_config",
        lambda: {
            "tracking_uri": "http://localhost:5001",
            "model_name": "foehncast-quality",
            "champion_alias": "champion",
        },
    )

    model_version = predict.get_serving_model_version()

    assert model_version == "5"
    assert logged["tracking_uri"] == "http://localhost:5001"
    assert logged["lookup"] == ("foehncast-quality", "champion")


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

    monkeypatch.setattr(predict, "get_production_model", lambda: FakeModel())
    monkeypatch.setattr(predict, "get_model_config", lambda: model_config)
    monkeypatch.setattr(
        predict, "get_inference_config", lambda: {"max_horizon_hours": 2}
    )
    monkeypatch.setattr(predict, "get_spots", lambda: [spot])
    monkeypatch.setattr(predict, "fetch_forecast", lambda lat, lon: forecast_df)
    monkeypatch.setattr(predict, "get_serving_model_version", lambda: "7")

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
    client = TestClient(serve.app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "model_version": "9"}


def test_spots_endpoint_lists_available_spots(
    monkeypatch: pytest.MonkeyPatch, spot: dict[str, object]
) -> None:
    monkeypatch.setattr(serve, "list_available_spots", lambda: [spot])
    client = TestClient(serve.app)

    response = client.get("/spots")

    assert response.status_code == 200
    assert response.json() == [spot]


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
    client = TestClient(serve.app)

    response = client.post("/predict", json={"spot_ids": ["silvaplana"]})

    assert response.status_code == 200
    assert response.json() == payload


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
        "returned_features": ["wind_speed_10m", "gust_factor"],
        "rows": [
            {
                "spot_id": "silvaplana",
                "wind_speed_10m": 14.0,
                "gust_factor": 1.5,
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
            "feature_names": ["wind_speed_10m", "gust_factor"],
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


def test_online_features_endpoint_returns_503_when_feast_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_unavailable(
        spot_ids: list[str] | None, feature_names: list[str] | None
    ) -> dict[str, object]:
        raise RuntimeError("Feast is not installed in this environment")

    monkeypatch.setattr(serve, "get_online_spot_features", raise_unavailable)
    client = TestClient(serve.app)

    response = client.post(
        "/features/online",
        json={"spot_ids": ["silvaplana"], "feature_names": ["wind_speed_10m"]},
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "Feast is not installed in this environment"}


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
