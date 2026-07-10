"""Rank spots by quality index, proximity, and duration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from foehncast.config import get_inference_config, get_spots
from foehncast.spots.distance import get_drive_minutes_to_spot

_RIDEABLE_QUALITY_THRESHOLD = 2.0
_MIN_DRIVE_HOURS = 0.25


@dataclass(slots=True)
class RankedSpot:
    spot_id: str
    spot_name: str
    quality_index: float
    drive_minutes: float
    session_hours: float
    ride_drive_ratio: float
    score: float


def compute_ride_drive_ratio(
    quality: float, drive_minutes: float, session_hours: float
) -> float:
    """Estimate ride value per drive-hour for a ranked spot."""
    if quality <= 0 or session_hours <= 0:
        return 0.0

    drive_hours = max(drive_minutes / 60.0, _MIN_DRIVE_HOURS)
    return float((quality * session_hours) / drive_hours)


def _normalize(values: list[float]) -> list[float]:
    if not values:
        return []

    min_value = min(values)
    max_value = max(values)
    if min_value == max_value:
        return [1.0 if max_value > 0 else 0.0 for _ in values]

    return [(value - min_value) / (max_value - min_value) for value in values]


def _session_hours(forecast: list[dict[str, Any]]) -> float:
    return float(
        sum(
            1
            for hour in forecast
            if hour["quality_index"] >= _RIDEABLE_QUALITY_THRESHOLD
        )
    )


def rank_spots(
    predictions: dict[str, Any], rider_config: dict[str, Any]
) -> list[RankedSpot]:
    """Rank predicted spot forecasts using quality, duration, and drive-time ROI."""
    ranking_weights = get_inference_config()["ranking_weights"]
    spots_by_id = {spot["id"]: spot for spot in get_spots()}
    candidate_rows: list[dict[str, Any]] = []

    for prediction in predictions.get("predictions", []):
        spot = spots_by_id[prediction["spot_id"]]
        forecast = prediction.get("forecast", [])
        quality_index = max(
            (float(hour["quality_index"]) for hour in forecast),
            default=0.0,
        )
        session_hours = _session_hours(forecast)
        drive_minutes = get_drive_minutes_to_spot(spot, rider_config)
        ride_drive_ratio = compute_ride_drive_ratio(
            quality=quality_index,
            drive_minutes=drive_minutes,
            session_hours=session_hours,
        )
        candidate_rows.append(
            {
                "spot_id": prediction["spot_id"],
                "spot_name": prediction["spot_name"],
                "quality_index": quality_index,
                "drive_minutes": drive_minutes,
                "session_hours": session_hours,
                "ride_drive_ratio": ride_drive_ratio,
            }
        )

    quality_scores = _normalize([row["quality_index"] for row in candidate_rows])
    ratio_scores = _normalize([row["ride_drive_ratio"] for row in candidate_rows])
    duration_scores = _normalize([row["session_hours"] for row in candidate_rows])
    ranked_spots: list[RankedSpot] = []

    for row, quality_score, ratio_score, duration_score in zip(
        candidate_rows,
        quality_scores,
        ratio_scores,
        duration_scores,
        strict=False,
    ):
        composite_score = (
            ranking_weights["quality_index"] * quality_score
            + ranking_weights["ride_drive_ratio"] * ratio_score
            + ranking_weights["duration_forecast"] * duration_score
        )
        ranked_spots.append(
            RankedSpot(
                spot_id=row["spot_id"],
                spot_name=row["spot_name"],
                quality_index=row["quality_index"],
                drive_minutes=row["drive_minutes"],
                session_hours=row["session_hours"],
                ride_drive_ratio=row["ride_drive_ratio"],
                score=float(composite_score),
            )
        )

    return sorted(ranked_spots, key=lambda spot: spot.score, reverse=True)
