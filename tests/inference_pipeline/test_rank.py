"""Tests for ranking and drive-time helpers."""

from __future__ import annotations

from typing import Any

import pytest

from foehncast.inference_pipeline import rank
from foehncast.spots import distance


def test_get_drive_minutes_calls_osrm_route(monkeypatch: pytest.MonkeyPatch) -> None:
    logged: dict[str, Any] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {"routes": [{"duration": 5400.0}]}

    def fake_get(
        url: str,
        params: dict[str, str],
        timeout: int,
        verify: str,
    ) -> FakeResponse:
        logged["url"] = url
        logged["params"] = params
        logged["timeout"] = timeout
        logged["verify"] = verify
        return FakeResponse()

    monkeypatch.setattr(
        distance,
        "get_api_config",
        lambda: {"osrm": {"base_url": "https://router.example/route/v1/driving"}},
    )
    monkeypatch.setattr(distance.requests, "get", fake_get)

    drive_minutes = distance.get_drive_minutes(47.02, 8.65, 46.45, 9.79)

    assert drive_minutes == 90.0
    assert (
        logged["url"] == "https://router.example/route/v1/driving/8.65,47.02;9.79,46.45"
    )
    assert logged["params"] == {"overview": "false"}
    assert logged["timeout"] == 30
    assert logged["verify"]


def test_compute_ride_drive_ratio_returns_zero_for_non_rideable_sessions() -> None:
    assert (
        rank.compute_ride_drive_ratio(
            quality=0.0, drive_minutes=45.0, session_hours=2.0
        )
        == 0.0
    )
    assert (
        rank.compute_ride_drive_ratio(
            quality=3.0, drive_minutes=45.0, session_hours=0.0
        )
        == 0.0
    )


def test_rank_spots_orders_by_weighted_score(monkeypatch: pytest.MonkeyPatch) -> None:
    predictions = {
        "predictions": [
            {
                "spot_id": "near-strong",
                "spot_name": "Near Strong",
                "forecast": [
                    {"time": "2025-01-01T00:00:00", "quality_index": 3.8},
                    {"time": "2025-01-01T01:00:00", "quality_index": 3.4},
                    {"time": "2025-01-01T02:00:00", "quality_index": 2.8},
                    {"time": "2025-01-01T03:00:00", "quality_index": 2.4},
                ],
            },
            {
                "spot_id": "far-peak",
                "spot_name": "Far Peak",
                "forecast": [
                    {"time": "2025-01-01T00:00:00", "quality_index": 4.0},
                    {"time": "2025-01-01T01:00:00", "quality_index": 2.3},
                ],
            },
            {
                "spot_id": "weak-local",
                "spot_name": "Weak Local",
                "forecast": [
                    {"time": "2025-01-01T00:00:00", "quality_index": 1.4},
                ],
            },
        ]
    }
    spots = [
        {"id": "near-strong", "name": "Near Strong", "lat": 0.0, "lon": 0.0},
        {"id": "far-peak", "name": "Far Peak", "lat": 0.0, "lon": 0.0},
        {"id": "weak-local", "name": "Weak Local", "lat": 0.0, "lon": 0.0},
    ]
    drive_minutes = {
        "near-strong": 30.0,
        "far-peak": 180.0,
        "weak-local": 20.0,
    }

    monkeypatch.setattr(
        rank,
        "get_inference_config",
        lambda: {
            "ranking_weights": {
                "quality_index": 0.6,
                "ride_drive_ratio": 0.3,
                "duration_forecast": 0.1,
            }
        },
    )
    monkeypatch.setattr(rank, "get_spots", lambda: spots)
    monkeypatch.setattr(
        rank,
        "get_drive_minutes_to_spot",
        lambda spot, rider_config: drive_minutes[spot["id"]],
    )

    ranked_spots = rank.rank_spots(
        predictions,
        rider_config={"home_lat": 47.02, "home_lon": 8.65},
    )

    assert [spot.spot_id for spot in ranked_spots] == [
        "near-strong",
        "far-peak",
        "weak-local",
    ]
    assert ranked_spots[0].session_hours == 4.0
    assert ranked_spots[0].drive_minutes == 30.0
    assert ranked_spots[0].score > ranked_spots[1].score > ranked_spots[2].score


def test_rank_spots_handles_empty_forecasts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        rank,
        "get_inference_config",
        lambda: {
            "ranking_weights": {
                "quality_index": 0.6,
                "ride_drive_ratio": 0.3,
                "duration_forecast": 0.1,
            }
        },
    )
    monkeypatch.setattr(
        rank,
        "get_spots",
        lambda: [{"id": "silvaplana", "name": "Silvaplana", "lat": 0.0, "lon": 0.0}],
    )
    monkeypatch.setattr(
        rank, "get_drive_minutes_to_spot", lambda spot, rider_config: 45.0
    )

    ranked_spots = rank.rank_spots(
        {
            "predictions": [
                {"spot_id": "silvaplana", "spot_name": "Silvaplana", "forecast": []}
            ]
        },
        rider_config={"home_lat": 47.02, "home_lon": 8.65},
    )

    assert len(ranked_spots) == 1
    assert ranked_spots[0].quality_index == 0.0
    assert ranked_spots[0].session_hours == 0.0
    assert ranked_spots[0].ride_drive_ratio == 0.0
