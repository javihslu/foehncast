"""Inference pipeline orchestration: scheduled prediction runs."""

from __future__ import annotations

import logging
from typing import Any


logger = logging.getLogger(__name__)


def run_inference_pipeline_step() -> dict[str, Any]:
    """Run inference for all configured spots and write the prediction log.

    Designed as an Airflow-callable: loads the champion model, calls
    ``predict_spots()`` for every configured spot, appends the prediction
    log, and emits drift metrics.  Returns the prediction payload dict.
    """
    from foehncast.inference_pipeline.predict import (
        predict_spots,
        write_latest_predictions,
    )
    from foehncast.monitoring.prediction_log import emit_prediction_drift_metrics

    log = logging.getLogger(__name__)
    log.info("Scheduled inference: running predictions for all spots")
    prediction_payload = predict_spots(spot_ids=None)

    n_spots = len(prediction_payload.get("predictions", []))
    model_version = prediction_payload.get("model_version", "unknown")
    log.info(
        "Scheduled inference: %d spots predicted with model v%s",
        n_spots,
        model_version,
    )

    # Persist snapshot for fast UI reads.
    write_latest_predictions(prediction_payload)

    emit_prediction_drift_metrics(
        prediction_payload,
        endpoint="scheduled",
    )
    log.info("Scheduled inference: prediction log and drift metrics updated")
    return prediction_payload
