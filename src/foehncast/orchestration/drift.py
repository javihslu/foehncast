"""Drift detection orchestration: feature and prediction drift steps."""

from __future__ import annotations

import logging
from typing import Any

from foehncast.config import get_spots
from foehncast.monitoring.drift import push_drift_metrics
from foehncast.orchestration.feature import (
    _emit_feature_drift_metrics,
    _read_optional_feature_slice,
)

logger = logging.getLogger(__name__)


def run_feature_drift_detection_step(
    dataset: str = "train",
) -> dict[str, Any]:
    """Detect data drift across all configured spots.

    Loads the curated feature store for each spot, splits into reference
    and current windows, runs ``detect_data_drift()``, and pushes StatsD
    metrics.  Returns a summary dict suitable for Airflow XCom.
    """
    log = logging.getLogger(__name__)
    spots = get_spots()
    spot_ids = [spot["id"] for spot in spots]
    drifted_spots: list[str] = []
    checked_spots: list[str] = []
    errors: dict[str, str] = {}

    for spot_id in spot_ids:
        try:
            features_df = _read_optional_feature_slice(spot_id, dataset)
            if features_df.empty or len(features_df) < 2:
                log.info("Drift check: skipping spot '%s' — insufficient data", spot_id)
                continue

            midpoint = len(features_df) // 2
            reference_df = features_df.iloc[:midpoint].copy()
            current_df = features_df.iloc[midpoint:].copy()

            if _emit_feature_drift_metrics(
                spot_id=spot_id,
                dataset=dataset,
                reference_df=reference_df,
                current_df=current_df,
            ):
                drifted_spots.append(spot_id)

            checked_spots.append(spot_id)
        except Exception as exc:
            log.exception(
                "Drift check: failed for spot '%s' in dataset '%s'",
                spot_id,
                dataset,
            )
            errors[spot_id] = str(exc)

    log.info(
        "Feature drift check: %d/%d spots checked, %d drifted",
        len(checked_spots),
        len(spot_ids),
        len(drifted_spots),
    )
    return {
        "dataset": dataset,
        "checked_spots": checked_spots,
        "drifted_spots": drifted_spots,
        "errors": errors,
    }


def run_prediction_drift_detection_step() -> dict[str, Any]:
    """Detect prediction drift from the logged prediction history.

    Loads the prediction event log, runs ``detect_prediction_drift()``,
    and pushes StatsD metrics.  Returns a summary dict.
    """
    from foehncast.monitoring.prediction_log import (
        read_prediction_history,
    )

    log = logging.getLogger(__name__)
    try:
        predictions_log = read_prediction_history(None)
        if predictions_log.empty or len(predictions_log) < 2:
            log.info("Prediction drift check: insufficient prediction history")
            return {"prediction_drift": None, "reason": "insufficient_data"}

        predictions_log.attrs.update(
            {"dataset_name": "inference_predictions", "dataset_version": "v1"}
        )
        from foehncast.monitoring.drift import detect_prediction_drift

        report = detect_prediction_drift(predictions_log)
        push_drift_metrics(report)
        log.info(
            "Prediction drift check: drift=%s, drifted_columns=%d/%d",
            report.dataset_drift,
            report.drifted_column_count,
            report.column_count,
        )
        return {
            "prediction_drift": report.dataset_drift,
            "drifted_column_count": report.drifted_column_count,
            "column_count": report.column_count,
            "share_of_drifted_columns": report.share_of_drifted_columns,
        }
    except Exception as exc:
        log.exception("Prediction drift check failed")
        return {"prediction_drift": None, "error": str(exc)}
