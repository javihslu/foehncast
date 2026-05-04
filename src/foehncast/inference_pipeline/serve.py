"""FastAPI prediction endpoint."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from foehncast.inference_pipeline.predict import (
    get_serving_model_version,
    list_available_spots,
    predict_spots,
)


class PredictionRequest(BaseModel):
    spot_ids: list[str] | None = None


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
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return app


app = create_app()
