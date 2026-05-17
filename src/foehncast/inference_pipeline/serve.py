"""FastAPI prediction and ranking endpoints."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict
import logging
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from foehncast.config import get_rider_config
from foehncast.inference_pipeline.demo import render_online_features_demo
from foehncast.inference_pipeline.online_features import get_online_spot_features
from foehncast.inference_pipeline.predict import (
    get_serving_model_alias,
    get_serving_model_version,
    list_available_spots,
    predict_spots,
)
from foehncast.inference_pipeline.rank import rank_spots
from foehncast.monitoring.prediction_log import emit_prediction_drift_metrics
from foehncast.monitoring.pipeline_prometheus import (
    CONTENT_TYPE_LATEST,
    render_feature_pipeline_prometheus_metrics,
    render_training_pipeline_prometheus_metrics,
)
from foehncast.monitoring.hosted_sync_prometheus import (
    render_hosted_sync_prometheus_metrics,
)
from foehncast.monitoring.inference_prometheus import (
    InferenceMetricsMiddleware,
    render_inference_prometheus_metrics,
)
from foehncast.monitoring.prediction_monitoring_prometheus import (
    record_prediction_monitoring_execution,
    record_prediction_monitoring_schedule,
    render_prediction_monitoring_prometheus_metrics,
)
from foehncast.monitoring.prediction_prometheus import (
    render_prediction_log_prometheus_metrics,
)
from foehncast.monitoring.hindcast import run_hindcast_validation
from foehncast.monitoring.hindcast_prometheus import (
    render_hindcast_prometheus_metrics,
)


logger = logging.getLogger(__name__)


class PredictionRequest(BaseModel):
    spot_ids: list[str] | None = None


class OnlineFeaturesRequest(BaseModel):
    spot_ids: list[str] | None = None
    feature_names: list[str] | None = None


def _not_found(exc: KeyError) -> HTTPException:
    message = exc.args[0] if exc.args else "Requested resource not found"
    return HTTPException(status_code=404, detail=message)


def _emit_prediction_monitoring(
    prediction_payload: dict[str, Any],
    *,
    endpoint: str,
    spot_ids: list[str] | None,
) -> None:
    try:
        emit_prediction_drift_metrics(
            prediction_payload,
            endpoint=endpoint,
            spot_ids=spot_ids,
        )
        record_prediction_monitoring_execution(endpoint, "succeeded")
    except Exception:
        record_prediction_monitoring_execution(endpoint, "failed")
        logger.exception(
            "Failed to emit prediction monitoring for endpoint '%s'",
            endpoint,
        )


def _schedule_prediction_monitoring(
    background_tasks: BackgroundTasks,
    prediction_payload: dict[str, Any],
    *,
    endpoint: str,
    spot_ids: list[str] | None,
) -> None:
    try:
        background_tasks.add_task(
            _emit_prediction_monitoring,
            prediction_payload,
            endpoint=endpoint,
            spot_ids=spot_ids,
        )
        record_prediction_monitoring_schedule(endpoint, "scheduled")
    except Exception:
        record_prediction_monitoring_schedule(endpoint, "failed")
        logger.exception(
            "Failed to schedule prediction monitoring for endpoint '%s'",
            endpoint,
        )


def _rank_response(prediction_payload: dict[str, Any]) -> dict[str, Any]:
    ranked_spots = rank_spots(prediction_payload, get_rider_config())
    return {
        "model_version": prediction_payload["model_version"],
        "ranked_spots": [asdict(spot) for spot in ranked_spots],
    }


def _metrics_payload() -> bytes:
    return (
        # Durable metrics: rendered from retained files and survive restarts.
        render_feature_pipeline_prometheus_metrics()
        + render_training_pipeline_prometheus_metrics()
        + render_prediction_log_prometheus_metrics()
        + render_hosted_sync_prometheus_metrics()
        + render_hindcast_prometheus_metrics()
        # Ephemeral metrics: rendered from in-memory counters and reset on restart.
        + render_prediction_monitoring_prometheus_metrics()
        + render_inference_prometheus_metrics()
    )


_HINDCAST_INTERVAL_SECONDS = 3600  # Run hindcast validation every hour.


def _run_hindcast_sync() -> None:
    """Run hindcast validation, logging any failures."""
    try:
        run_hindcast_validation()
    except Exception:
        logger.exception("Hindcast validation failed")


async def _hindcast_background_loop() -> None:
    """Periodically run hindcast validation in a thread to avoid blocking."""
    while True:
        await asyncio.to_thread(_run_hindcast_sync)
        await asyncio.sleep(_HINDCAST_INTERVAL_SECONDS)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    task = asyncio.create_task(_hindcast_background_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


def create_app() -> FastAPI:
    """Build the serving application for health and inference endpoints."""
    app = FastAPI(title="FoehnCast API", version="0.1.0", lifespan=_lifespan)
    app.add_middleware(InferenceMetricsMiddleware)

    @app.get("/health")
    def health() -> dict[str, str]:
        try:
            return {
                "status": "healthy",
                "model_alias": get_serving_model_alias(),
                "model_version": get_serving_model_version(),
            }
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/spots")
    def spots() -> list[dict[str, Any]]:
        return list_available_spots()

    @app.post("/predict")
    def predict(
        request: PredictionRequest,
        background_tasks: BackgroundTasks,
    ) -> dict[str, Any]:
        try:
            prediction_payload = predict_spots(request.spot_ids)
            _schedule_prediction_monitoring(
                background_tasks,
                prediction_payload,
                endpoint="predict",
                spot_ids=request.spot_ids,
            )
            return prediction_payload
        except KeyError as exc:
            raise _not_found(exc) from exc

    @app.post("/rank")
    def rank(
        request: PredictionRequest,
        background_tasks: BackgroundTasks,
    ) -> dict[str, Any]:
        try:
            prediction_payload = predict_spots(request.spot_ids)
            _schedule_prediction_monitoring(
                background_tasks,
                prediction_payload,
                endpoint="rank",
                spot_ids=request.spot_ids,
            )
            return _rank_response(prediction_payload)
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

    @app.get("/metrics")
    def metrics() -> Response:
        return Response(
            content=_metrics_payload(),
            headers={"Content-Type": CONTENT_TYPE_LATEST},
        )

    return app


app = create_app()
