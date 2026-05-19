"""Helpers for the Streamlit live-demo dashboard."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

import pandas as pd

from foehncast.config import get_inference_config, get_rider_config
from foehncast.inference_pipeline.predict import (
    list_available_spots,
    predict_spots,
    read_latest_predictions,
)
from foehncast.inference_pipeline.rank import rank_spots

_RIDEABLE_QUALITY_THRESHOLD = 2.0
_QUALITY_LABELS = {
    0: "Unsafe",
    1: "Too Light",
    2: "Marginal",
    3: "Good Enough",
    4: "Fun Day",
    5: "Perfect Storm",
}


def list_dashboard_spots() -> list[dict[str, Any]]:
    """Return the configured spots available to the dashboard."""
    return list_available_spots()


def quality_bucket(value: float) -> int:
    """Round a continuous quality score into the nearest rider-facing band."""
    rounded = int(round(float(value)))
    return min(max(rounded, 0), 5)


def quality_label(value: float) -> str:
    """Return the rider-facing label for a quality score."""
    return _QUALITY_LABELS[quality_bucket(value)]


def build_forecast_frame(prediction: dict[str, Any]) -> pd.DataFrame:
    """Convert a spot prediction payload into a chart-friendly dataframe."""
    forecast_rows = prediction.get("forecast", [])
    if not forecast_rows:
        return pd.DataFrame(
            columns=[
                "time",
                "display_time",
                "quality_index",
                "quality_label",
                "rideable",
            ]
        )

    frame = pd.DataFrame(forecast_rows)
    frame["time"] = pd.to_datetime(frame["time"])
    frame["quality_index"] = frame["quality_index"].astype(float)
    frame = frame.sort_values("time").reset_index(drop=True)
    frame["quality_label"] = frame["quality_index"].map(quality_label)
    frame["rideable"] = frame["quality_index"] >= _RIDEABLE_QUALITY_THRESHOLD
    frame["display_time"] = frame["time"].dt.strftime("%a %d %b %H:%M")
    return frame


def summarize_forecast(prediction: dict[str, Any]) -> dict[str, Any]:
    """Summarize the strongest part of a spot forecast for dashboard cards."""
    frame = build_forecast_frame(prediction)
    if frame.empty:
        return {
            "peak_quality": 0.0,
            "peak_label": quality_label(0.0),
            "peak_time": None,
            "peak_time_label": "No forecast rows",
            "rideable_hours": 0,
            "forecast_rows": 0,
        }

    peak_row = frame.loc[frame["quality_index"].idxmax()]
    return {
        "peak_quality": float(peak_row["quality_index"]),
        "peak_label": str(peak_row["quality_label"]),
        "peak_time": peak_row["time"].isoformat(),
        "peak_time_label": str(peak_row["display_time"]),
        "rideable_hours": int(frame["rideable"].sum()),
        "forecast_rows": int(len(frame)),
    }


def build_ranking_frame(ranked_spots: list[dict[str, Any]]) -> pd.DataFrame:
    """Build a compact dataframe for the ranked recommendations table."""
    rows: list[dict[str, object]] = []
    for position, spot in enumerate(ranked_spots, start=1):
        rows.append(
            {
                "Rank": position,
                "Spot": spot["spot_name"],
                "Signal": spot["quality_label"],
                "Peak quality": round(float(spot["quality_index"]), 2),
                "Rideable hrs": int(spot["rideable_hours"]),
                "Drive min": round(float(spot["drive_minutes"]), 1),
                "Session hrs": round(float(spot["session_hours"]), 1),
                "Ride/drive": round(float(spot["ride_drive_ratio"]), 2),
                "Score": round(float(spot["score"]), 3),
            }
        )
    return pd.DataFrame(rows)


def horizon_caption(hours: int) -> str:
    """Describe the currently supported live forecast window."""
    unit = "hour" if hours == 1 else "hours"
    return f"Forecast window: {hours} {unit} from the current Open-Meteo pull."


def load_dashboard_data(spot_ids: list[str] | None = None) -> dict[str, Any]:
    """Load live predictions, rankings, and demo metadata for the Streamlit UI.

    Prefers the pre-computed prediction snapshot written by the inference
    pipeline.  Falls back to live inference only when the snapshot is
    missing, stale, or doesn't cover the requested spots.
    """
    resolved_spot_ids = spot_ids or None
    available_spots = list_dashboard_spots()
    rider_profile = get_rider_config()

    # Try cached snapshot first (sub-ms read vs multi-second live inference).
    predictions = read_latest_predictions()
    if predictions is not None and resolved_spot_ids is not None:
        # Verify the snapshot covers all requested spots.
        snapshot_spot_ids = {p["spot_id"] for p in predictions.get("predictions", [])}
        if not set(resolved_spot_ids).issubset(snapshot_spot_ids):
            predictions = None
        else:
            # Filter the snapshot to only the requested spots.
            predictions = {
                "model_version": predictions["model_version"],
                "predictions": [
                    p
                    for p in predictions["predictions"]
                    if p["spot_id"] in set(resolved_spot_ids)
                ],
            }
    if predictions is None:
        predictions = predict_spots(resolved_spot_ids)

    ranked_spots = rank_spots(predictions, rider_profile)
    prediction_by_spot_id = {
        prediction["spot_id"]: prediction for prediction in predictions["predictions"]
    }
    ranked_cards: list[dict[str, Any]] = []

    for ranked_spot in ranked_spots:
        summary = summarize_forecast(prediction_by_spot_id[ranked_spot.spot_id])
        ranked_cards.append(
            {
                **asdict(ranked_spot),
                "quality_label": quality_label(ranked_spot.quality_index),
                **summary,
            }
        )

    return {
        "available_spots": available_spots,
        "model_version": predictions["model_version"],
        "rider_profile": rider_profile,
        "horizon_hours": int(get_inference_config()["max_horizon_hours"]),
        "predictions": predictions["predictions"],
        "ranked_spots": ranked_cards,
    }
