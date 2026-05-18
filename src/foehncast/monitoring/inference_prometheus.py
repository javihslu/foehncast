"""HTTP request metrics for the inference API."""

from __future__ import annotations

import time
from collections.abc import Callable, Awaitable

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


_registry = CollectorRegistry()

request_duration = Histogram(
    "foehncast_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint", "status"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=_registry,
)

request_total = Counter(
    "foehncast_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
    registry=_registry,
)

model_confidence = Gauge(
    "foehncast_inference_model_confidence",
    "Latest model confidence per spot (mean forecast quality index in [0,1])",
    ["spot_id"],
    registry=_registry,
)


def observe_model_confidence(spot_id: str, value: float) -> None:
    """Record latest model confidence for a spot.

    Clamps the value to [0, 1] so the gauge is always a valid confidence score.
    """
    bounded = max(0.0, min(1.0, float(value)))
    model_confidence.labels(spot_id).set(bounded)


def _normalize_path(path: str) -> str:
    """Collapse path to the route pattern to avoid cardinality explosion."""
    known = {
        "/health",
        "/spots",
        "/predict",
        "/rank",
        "/features/online",
        "/features/online/demo",
        "/metrics",
    }
    return path if path in known else "other"


class InferenceMetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start

        endpoint = _normalize_path(request.url.path)
        status = str(response.status_code)
        request_duration.labels(request.method, endpoint, status).observe(duration)
        request_total.labels(request.method, endpoint, status).inc()

        return response


def render_inference_prometheus_metrics() -> bytes:
    return generate_latest(_registry)
