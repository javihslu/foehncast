"""Drift detection orchestration: feature and prediction drift steps."""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from foehncast.config import get_model_config, get_spots
from foehncast.monitoring.drift import detect_model_feature_drift, push_drift_metrics
from foehncast.orchestration.feature import (
    _emit_feature_drift_metrics,
    _read_optional_feature_slice,
)

logger = logging.getLogger(__name__)


def run_feature_drift_detection_step(
    dataset: str = "train",
    reference_dataset: str | None = None,
) -> dict[str, Any]:
    """Detect data drift across all configured spots.

    With ``reference_dataset`` set, that slice is compared against the
    ``dataset`` slice (the cloud job compares train vs forecast). Otherwise
    the single dataset is split at its midpoint, as on the local stack.
    Pushes StatsD metrics and returns a summary dict.
    """
    spots = get_spots()
    spot_ids = [spot["id"] for spot in spots]
    drifted_spots: list[str] = []
    checked_spots: list[str] = []
    errors: dict[str, str] = {}
    comparison = f"{reference_dataset}-vs-{dataset}" if reference_dataset else dataset

    for spot_id in spot_ids:
        try:
            features_df = _read_optional_feature_slice(spot_id, dataset)
            if features_df.empty or len(features_df) < 2:
                logger.info(
                    "Drift check: skipping spot '%s' — insufficient data", spot_id
                )
                continue

            if reference_dataset:
                reference_df = _read_optional_feature_slice(spot_id, reference_dataset)
                if reference_df.empty:
                    logger.info(
                        "Drift check: skipping spot '%s' — no reference data", spot_id
                    )
                    continue
                current_df = features_df.copy()
            else:
                midpoint = len(features_df) // 2
                reference_df = features_df.iloc[:midpoint].copy()
                current_df = features_df.iloc[midpoint:].copy()

            if _emit_feature_drift_metrics(
                spot_id=spot_id,
                dataset=comparison,
                reference_df=reference_df,
                current_df=current_df,
            ):
                drifted_spots.append(spot_id)

            checked_spots.append(spot_id)
        except Exception as exc:
            logger.exception(
                "Drift check: failed for spot '%s' in dataset '%s'",
                spot_id,
                dataset,
            )
            errors[spot_id] = str(exc)

    logger.info(
        "Feature drift check (%s): %d/%d spots checked, %d drifted",
        comparison,
        len(checked_spots),
        len(spot_ids),
        len(drifted_spots),
    )
    return {
        "dataset": dataset,
        "comparison": comparison,
        "checked_spots": checked_spots,
        "drifted_spots": drifted_spots,
        "errors": errors,
    }


def _read_all_spot_features(dataset: str) -> pd.DataFrame:
    """Concatenate stored features for one dataset across all configured spots."""
    frames: list[pd.DataFrame] = []
    for spot in get_spots():
        features_df = _read_optional_feature_slice(spot["id"], dataset)
        if not features_df.empty:
            frames.append(features_df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def run_forecast_feature_drift_detection_step(
    dataset: str = "forecast",
    reference_dataset: str = "train",
) -> dict[str, Any]:
    """Detect dataset-level drift between the training reference and forecast.

    Compares the two datasets as a whole, scoped to the configured model feature
    set (``config.yaml`` model.features), so ``share_of_drifted_columns`` (and
    the UI Confidence chip that reads it) is resolved over the full feature set
    rather than a narrow overlap. This is distinct from the per-spot feature
    drift check. Columns are intersected with what each dataset carries, so a
    narrow reference does not crash the comparison.
    """
    try:
        feature_columns = list(get_model_config().get("features", []))
        reference_df = _read_all_spot_features(reference_dataset)
        current_df = _read_all_spot_features(dataset)
        report = detect_model_feature_drift(
            reference_df,
            current_df,
            feature_columns,
            dataset_name="forecast features",
            dataset_version="v1",
        )
        if report is None:
            logger.info(
                "Forecast feature drift check: nothing comparable "
                "(reference=%d rows, forecast=%d rows)",
                len(reference_df),
                len(current_df),
            )
            return {"forecast_feature_drift": None, "reason": "no_comparable_columns"}

        push_drift_metrics(report)
        logger.info(
            "Forecast feature drift check: drift=%s, drifted_columns=%d/%d",
            report.dataset_drift,
            report.drifted_column_count,
            report.column_count,
        )
        return {
            "forecast_feature_drift": report.dataset_drift,
            "compared_column_count": report.column_count,
            "drifted_column_count": report.drifted_column_count,
            "share_of_drifted_columns": report.share_of_drifted_columns,
        }
    except Exception as exc:
        logger.exception("Forecast feature drift check failed")
        return {"forecast_feature_drift": None, "error": str(exc)}


def run_prediction_drift_detection_step() -> dict[str, Any]:
    """Detect prediction drift from the logged prediction history.

    Loads the prediction event log, runs ``detect_prediction_drift()``,
    and pushes StatsD metrics.  Returns a summary dict.
    """
    from foehncast.monitoring.prediction_log import (
        read_prediction_history,
    )

    try:
        predictions_log = read_prediction_history(None)
        if predictions_log.empty or len(predictions_log) < 2:
            logger.info("Prediction drift check: insufficient prediction history")
            return {"prediction_drift": None, "reason": "insufficient_data"}

        predictions_log.attrs.update(
            {"dataset_name": "inference_predictions", "dataset_version": "v1"}
        )
        from foehncast.monitoring.drift import detect_prediction_drift

        report = detect_prediction_drift(predictions_log)
        push_drift_metrics(report)
        logger.info(
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
        logger.exception("Prediction drift check failed")
        return {"prediction_drift": None, "error": str(exc)}
