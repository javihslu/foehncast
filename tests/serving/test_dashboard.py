"""Tests for Streamlit dashboard helper logic."""

from __future__ import annotations

import pytest

from foehncast.inference_pipeline import dashboard
from foehncast.inference_pipeline.rank import RankedSpot


def test_quality_label_rounds_to_nearest_band() -> None:
    assert dashboard.quality_label(0.2) == "Unsafe"
    assert dashboard.quality_label(1.8) == "Marginal"
    assert dashboard.quality_label(3.6) == "Fun Day"


def test_build_forecast_frame_sorts_rows_and_marks_rideable_windows() -> None:
    frame = dashboard.build_forecast_frame(
        {
            "forecast": [
                {"time": "2025-01-01T03:00:00+00:00", "quality_index": 4.2},
                {"time": "2025-01-01T01:00:00+00:00", "quality_index": 1.8},
            ]
        }
    )

    assert list(frame["quality_index"]) == [1.8, 4.2]
    assert list(frame["quality_label"]) == ["Marginal", "Fun Day"]
    assert list(frame["rideable"]) == [False, True]
    assert frame.iloc[0]["display_time"].endswith("01:00")


def test_summarize_forecast_returns_defaults_for_empty_predictions() -> None:
    summary = dashboard.summarize_forecast({"forecast": []})

    assert summary == {
        "peak_quality": 0.0,
        "peak_label": "Unsafe",
        "peak_time": None,
        "peak_time_label": "No forecast rows",
        "rideable_hours": 0,
        "forecast_rows": 0,
    }


def test_load_dashboard_data_combines_predictions_rankings_and_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        dashboard,
        "list_dashboard_spots",
        lambda: [{"id": "silvaplana", "name": "Silvaplana"}],
    )
    monkeypatch.setattr(
        dashboard,
        "get_rider_config",
        lambda: {
            "weight_kg": 80,
            "home_location": "Schwyz",
            "home_lat": 47.02,
            "home_lon": 8.65,
            "quiver_m2": [5, 7, 8, 10, 12],
        },
    )
    monkeypatch.setattr(
        dashboard,
        "predict_spots",
        lambda spot_ids: {
            "model_version": "11",
            "predictions": [
                {
                    "spot_id": "silvaplana",
                    "spot_name": "Silvaplana",
                    "forecast": [
                        {
                            "time": "2025-01-01T00:00:00+00:00",
                            "quality_index": 2.2,
                        },
                        {
                            "time": "2025-01-01T01:00:00+00:00",
                            "quality_index": 3.4,
                        },
                    ],
                }
            ],
        },
    )
    monkeypatch.setattr(
        dashboard,
        "rank_spots",
        lambda predictions, rider_config: [
            RankedSpot(
                spot_id="silvaplana",
                spot_name="Silvaplana",
                quality_index=3.4,
                drive_minutes=95.0,
                session_hours=2.0,
                ride_drive_ratio=4.29,
                score=1.0,
            )
        ],
    )
    monkeypatch.setattr(
        dashboard,
        "get_inference_config",
        lambda: {"max_horizon_hours": 14},
    )

    payload = dashboard.load_dashboard_data(["silvaplana"])

    assert payload["model_version"] == "11"
    assert payload["horizon_hours"] == 14
    assert payload["rider_profile"]["home_location"] == "Schwyz"
    assert payload["available_spots"] == [{"id": "silvaplana", "name": "Silvaplana"}]
    assert payload["ranked_spots"][0]["spot_id"] == "silvaplana"
    assert payload["ranked_spots"][0]["quality_label"] == "Good Enough"
    assert payload["ranked_spots"][0]["rideable_hours"] == 2
    assert payload["ranked_spots"][0]["peak_time_label"].endswith("01:00")

    ranking_frame = dashboard.build_ranking_frame(payload["ranked_spots"])
    assert list(ranking_frame["Spot"]) == ["Silvaplana"]
    assert list(ranking_frame["Signal"]) == ["Good Enough"]


def test_horizon_caption_describes_hour_based_contract() -> None:
    assert "14 hours" in dashboard.horizon_caption(14)
