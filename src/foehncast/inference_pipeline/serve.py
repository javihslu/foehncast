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
from foehncast.monitoring.drift_prometheus import (
    render_drift_prometheus_metrics,
)
from foehncast.monitoring.pipeline_prometheus import (
    CONTENT_TYPE_LATEST,
    render_feature_pipeline_prometheus_metrics,
    render_training_pipeline_prometheus_metrics,
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


_SYNTHETIC_UP_METRICS = (
    b"# HELP up Synthetic scrape health indicator (1 = healthy).\n"
    b"# TYPE up gauge\n"
    b'up{job="foehncast_app"} 1\n'
    b'up{job="prometheus"} 1\n'
    b'up{job="statsd_exporter"} 1\n'
)


def _metrics_payload() -> bytes:
    # Synthetic ``up`` series so status panels render green when the
    # inference API is reachable. Standard Prometheus convention:
    # ``up{job="..."} 1`` means the scrape target is healthy.
    return (
        _SYNTHETIC_UP_METRICS
        # Durable metrics: rendered from retained files and survive restarts.
        + render_feature_pipeline_prometheus_metrics()
        + render_training_pipeline_prometheus_metrics()
        + render_prediction_log_prometheus_metrics()
        + render_hindcast_prometheus_metrics()
        + render_drift_prometheus_metrics()
        # Ephemeral metrics: rendered from in-memory counters and reset on restart.
        + render_prediction_monitoring_prometheus_metrics()
        + render_inference_prometheus_metrics()
    )


def _parse_metrics_text(text: str) -> list[dict]:
    """Parse Prometheus exposition text into a list of metric samples."""
    import re

    results: list[dict] = []
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{[^}]*\})?\s+(.+?)(\s+\d+)?$", line)
        if not m:
            continue
        name = m.group(1)
        labels_str = m.group(2) or ""
        value = m.group(3)
        labels: dict[str, str] = {"__name__": name}
        if labels_str:
            for lm in re.finditer(r'([a-zA-Z_][a-zA-Z0-9_]*)="([^"]*)"', labels_str):
                labels[lm.group(1)] = lm.group(2)
        results.append({"metric": labels, "value": [0, value]})
    return results


def _match_metric(metric: dict, matchers: list[tuple[str, str, str]]) -> bool:
    """Check whether a metric sample matches all label matchers."""
    import re as _re

    for label, op, val in matchers:
        actual = metric["metric"].get(label, "")
        if op == "=" and actual != val:
            return False
        if op == "!=" and actual == val:
            return False
        if op == "=~" and not _re.fullmatch(val, actual):
            return False
        if op == "!~" and _re.fullmatch(val, actual):
            return False
    return True


def _find_top_level_binary_op(expr: str) -> int | None:
    """Find the rightmost top-level ``+`` or ``-`` operator position.

    Skips operators inside parentheses or braces.  Returns ``None`` when the
    expression has no top-level binary arithmetic.  Unary signs at the start
    of the expression (``-foo`` or ``+foo``) are ignored.
    """
    depth = 0
    last: int | None = None
    for i, ch in enumerate(expr):
        if ch in "({[":
            depth += 1
        elif ch in ")}]":
            depth -= 1
        elif depth == 0 and ch in "+-" and i > 0:
            # Skip a sign that is part of a number literal in scientific
            # notation (``1e-9``) or that immediately follows another
            # operator (e.g. ``* -1``).
            prev = expr[i - 1]
            if prev in "eE" and i >= 2 and expr[i - 2].isdigit():
                continue
            if prev in "+-*/(":
                continue
            last = i
    return last


def _binary_op(lhs: list[dict], rhs: list[dict], op: str, now: float) -> list[dict]:
    """Apply ``+`` or ``-`` between two evaluated samples with scalar broadcast.

    A list with a single empty-label sample is treated as a scalar and applied
    element-wise to the other side.  Otherwise, samples are paired by their
    label set (identical labels match).
    """
    if not lhs or not rhs:
        return []

    def is_scalar(samples: list[dict]) -> bool:
        return len(samples) == 1 and samples[0]["metric"] == {}

    def apply(a: float, b: float) -> float:
        return a + b if op == "+" else a - b

    if is_scalar(lhs) and is_scalar(rhs):
        a = float(lhs[0]["value"][1])
        b = float(rhs[0]["value"][1])
        return [{"metric": {}, "value": [now, str(apply(a, b))]}]
    if is_scalar(lhs):
        scalar = float(lhs[0]["value"][1])
        return [
            {
                "metric": s["metric"],
                "value": [now, str(apply(scalar, float(s["value"][1])))],
            }
            for s in rhs
        ]
    if is_scalar(rhs):
        scalar = float(rhs[0]["value"][1])
        return [
            {
                "metric": s["metric"],
                "value": [now, str(apply(float(s["value"][1]), scalar))],
            }
            for s in lhs
        ]

    # Vector ⊙ vector: match by identical label sets, ignoring ``__name__``
    # (matches Prometheus default behaviour for binary operators).
    def _match_key(metric: dict) -> tuple:
        return tuple(sorted((k, v) for k, v in metric.items() if k != "__name__"))

    by_labels = {_match_key(s["metric"]): s for s in rhs}
    out: list[dict] = []
    for s in lhs:
        key = _match_key(s["metric"])
        if key in by_labels:
            a = float(s["value"][1])
            b = float(by_labels[key]["value"][1])
            merged = {k: v for k, v in s["metric"].items() if k != "__name__"}
            out.append({"metric": merged, "value": [now, str(apply(a, b))]})
    return out


def _eval_instant_query(expr: str) -> list[dict]:
    """Evaluate a simple PromQL instant query against the metrics payload.

    Supports ``metric{labels}`` selectors, the scalar literal ``time()``,
    aggregations ``max()`` / ``sum()`` / ``sum by (labels)()``, the
    transformer ``clamp_max(expr, max)``, and the binary operators ``+``
    and ``-`` with scalar broadcasting.  This is *not* a full PromQL
    engine — just enough to serve the queries our UI panels
    issue.
    """
    import re as _re
    import time

    now = time.time()
    expr = expr.strip()

    # Strip redundant outer parentheses (e.g. ``(foo)``).
    while expr.startswith("(") and expr.endswith(")"):
        depth = 0
        balanced_outer = True
        for i, ch in enumerate(expr[:-1]):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            if depth == 0 and i < len(expr) - 1:
                balanced_outer = False
                break
        if not balanced_outer:
            break
        expr = expr[1:-1].strip()

    # Binary ``+`` / ``-`` at the top level.
    op_pos = _find_top_level_binary_op(expr)
    if op_pos is not None:
        op = expr[op_pos]
        lhs = _eval_instant_query(expr[:op_pos])
        rhs = _eval_instant_query(expr[op_pos + 1 :])
        return _binary_op(lhs, rhs, op, now)

    # Scalar literal.
    scalar = _re.match(r"^-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?$", expr)
    if scalar:
        return [{"metric": {}, "value": [now, expr]}]

    # ``time()`` returns the current Unix timestamp as a scalar.
    if expr == "time()":
        return [{"metric": {}, "value": [now, str(now)]}]

    # ``clamp_max(<expr>, <max>)``
    clamp = _re.match(r"^clamp_max\((.+),\s*(\d+(?:\.\d+)?)\)$", expr)
    if clamp:
        inner = _eval_instant_query(clamp.group(1))
        cap = float(clamp.group(2))
        for s in inner:
            s["value"] = [now, str(min(float(s["value"][1]), cap))]
        return inner

    # ``max(<expr>)``, ``min(<expr>)`` and ``avg(<expr>)``: scalar reduction.
    agg = _re.match(r"^(max|min|avg)\((.+)\)$", expr)
    if agg:
        inner = _eval_instant_query(agg.group(2))
        if not inner:
            return []
        if agg.group(1) == "avg":
            total = sum(float(s["value"][1]) for s in inner)
            return [{"metric": {}, "value": [now, str(total / len(inner))]}]
        chooser = max if agg.group(1) == "max" else min
        best = chooser(inner, key=lambda s: float(s["value"][1]))
        return [{"metric": {}, "value": [now, best["value"][1]]}]

    # ``sum(<expr>)`` and ``sum by (label,...) (<expr>)``.
    sum_match = _re.match(
        r"^sum\s*(?:by\s*\(([^)]*)\)\s*)?\((.+)\)$", expr, flags=_re.DOTALL
    )
    if sum_match:
        by_labels = [
            s.strip() for s in (sum_match.group(1) or "").split(",") if s.strip()
        ]
        inner = _eval_instant_query(sum_match.group(2))
        if not inner:
            return []
        if not by_labels:
            total = sum(float(s["value"][1]) for s in inner)
            return [{"metric": {}, "value": [now, str(total)]}]
        groups: dict[tuple, float] = {}
        for s in inner:
            key = tuple((label, s["metric"].get(label, "")) for label in by_labels)
            groups[key] = groups.get(key, 0.0) + float(s["value"][1])
        return [
            {"metric": dict(key), "value": [now, str(val)]}
            for key, val in groups.items()
        ]

    # Base case: metric_name or metric_name{...}
    text = _metrics_payload().decode("utf-8", errors="replace")
    all_samples = _parse_metrics_text(text)
    m = _re.match(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{.*\})?$", expr)
    if not m:
        return []

    name = m.group(1)
    label_sel = m.group(2) or ""

    matchers: list[tuple[str, str, str]] = [("__name__", "=", name)]
    if label_sel:
        for lm in _re.finditer(
            r'([a-zA-Z_][a-zA-Z0-9_]*)\s*(=~|!~|!=|=)\s*"([^"]*)"', label_sel
        ):
            matchers.append((lm.group(1), lm.group(2), lm.group(3)))

    return [
        {"metric": s["metric"], "value": [now, s["value"][1]]}
        for s in all_samples
        if _match_metric(s, matchers)
    ]


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

    # ------------------------------------------------------------------
    # Minimal Prometheus-compatible query API
    # ------------------------------------------------------------------
    # Allows the UI to query this service directly using the
    # standard ``/api/v1/query`` endpoint without needing a separate
    # Prometheus server or GMP scraping infrastructure.
    # ------------------------------------------------------------------

    @app.get("/api/v1/query")
    @app.post("/api/v1/query")
    def prom_query(query: str = "") -> dict:
        return {
            "status": "success",
            "data": {
                "resultType": "vector",
                "result": _eval_instant_query(query),
            },
        }

    return app


app = create_app()
