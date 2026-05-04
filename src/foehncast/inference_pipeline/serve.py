"""FastAPI prediction and ranking endpoints."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from foehncast.config import get_rider_config
from foehncast.inference_pipeline.demo import render_online_features_demo
from foehncast.inference_pipeline.online_features import get_online_spot_features
from foehncast.inference_pipeline.predict import (
    get_serving_model_version,
    list_available_spots,
    predict_spots,
)
from foehncast.inference_pipeline.rank import rank_spots


class PredictionRequest(BaseModel):
    spot_ids: list[str] | None = None


class OnlineFeaturesRequest(BaseModel):
    spot_ids: list[str] | None = None
    feature_names: list[str] | None = None


def _not_found(exc: KeyError) -> HTTPException:
    message = exc.args[0] if exc.args else "Requested resource not found"
    return HTTPException(status_code=404, detail=message)


def _rank_response(spot_ids: list[str] | None) -> dict[str, Any]:
    prediction_payload = predict_spots(spot_ids)
    ranked_spots = rank_spots(prediction_payload, get_rider_config())
    return {
        "model_version": prediction_payload["model_version"],
        "ranked_spots": [asdict(spot) for spot in ranked_spots],
    }


def create_app() -> FastAPI:
    """Build the serving application for health and inference endpoints."""
    app = FastAPI(title="FoehnCast API", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        try:
            return {
                "status": "healthy",
                "model_version": get_serving_model_version(),
            }
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/spots")
    def spots() -> list[dict[str, Any]]:
        return list_available_spots()

    @app.post("/predict")
    def predict(request: PredictionRequest) -> dict[str, Any]:
        try:
            return predict_spots(request.spot_ids)
        except KeyError as exc:
            raise _not_found(exc) from exc

    @app.post("/rank")
    def rank(request: PredictionRequest) -> dict[str, Any]:
        try:
            return _rank_response(request.spot_ids)
        except KeyError as exc:
            raise _not_found(exc) from exc

    @app.post("/features/online")
    def online_features(request: OnlineFeaturesRequest) -> dict[str, Any]:
        try:
            return get_online_spot_features(request.spot_ids, request.feature_names)
        except KeyError as exc:
            raise _not_found(exc) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/features/online/demo", response_class=HTMLResponse)
    def online_features_demo() -> str:
        return render_online_features_demo()

    return app


app = create_app()
