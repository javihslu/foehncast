"""Tests for hindcast validation — comparing predictions against observed weather."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pandas as pd

from foehncast.monitoring.hindcast import (
    _eligible_predictions,
    read_hindcast_result,
    run_hindcast_validation,
)

_NOOP_WRITE = patch(
    "foehncast.monitoring.hindcast._write_hindcast_result",
    lambda result, path=None: None,
)


def _make_prediction_history(
    *,
    n_rows: int = 5,
    spot_id: str = "silvaplana",
    forecast_hours_ago: int = 200,
    quality_index: float = 3.0,
) -> pd.DataFrame:
    now = datetime.now(tz=UTC)
    base = now - timedelta(hours=forecast_hours_ago)
    return pd.DataFrame(
        {
            "prediction_timestamp": [
                (base - timedelta(hours=6)).isoformat() for _ in range(n_rows)
            ],
            "forecast_time": [
                (base + timedelta(hours=i)).isoformat() for i in range(n_rows)
            ],
            "quality_index": [quality_index] * n_rows,
            "endpoint": ["predict"] * n_rows,
            "model_version": ["3"] * n_rows,
            "spot_id": [spot_id] * n_rows,
            "spot_name": ["Silvaplana"] * n_rows,
            "requested_spot_ids": ["silvaplana"] * n_rows,
        }
    )


class TestEligiblePredictions:
    def test_filters_future_forecasts(self) -> None:
        history = _make_prediction_history(forecast_hours_ago=200)
        eligible = _eligible_predictions(history, buffer_hours=120)
        assert len(eligible) == 5

    def test_excludes_recent_forecasts(self) -> None:
        history = _make_prediction_history(forecast_hours_ago=24)
        eligible = _eligible_predictions(history, buffer_hours=120)
        assert len(eligible) == 0

    def test_empty_history(self) -> None:
        history = pd.DataFrame(columns=list(_make_prediction_history().columns))
        eligible = _eligible_predictions(history, buffer_hours=120)
        assert len(eligible) == 0


class TestRunHindcastValidation:
    def test_returns_empty_when_no_predictions(self) -> None:
        with (
            patch(
                "foehncast.monitoring.hindcast.read_prediction_history",
                return_value=pd.DataFrame(),
            ),
            _NOOP_WRITE,
        ):
            result = run_hindcast_validation()
        assert result["validated_count"] == 0
        assert result["accuracy"] is None
        assert result["mae"] is None
        assert result["validated_at"] is not None

    def test_returns_empty_when_no_eligible(self) -> None:
        history = _make_prediction_history(forecast_hours_ago=24)
        with (
            patch(
                "foehncast.monitoring.hindcast.read_prediction_history",
                return_value=history,
            ),
            _NOOP_WRITE,
        ):
            result = run_hindcast_validation(buffer_hours=120)
        assert result["validated_count"] == 0

    def test_computes_metrics_with_matching_data(self) -> None:
        now = datetime.now(tz=UTC)
        # Truncate to the hour so prediction and observation timestamps align
        # after the round("h") step in run_hindcast_validation.
        forecast_base = (now - timedelta(hours=200)).replace(
            minute=0, second=0, microsecond=0
        )

        history = pd.DataFrame(
            {
                "prediction_timestamp": [
                    (forecast_base - timedelta(hours=6)).isoformat()
                ],
                "forecast_time": [forecast_base.isoformat()],
                "quality_index": [3.0],
                "endpoint": ["predict"],
                "model_version": ["3"],
                "spot_id": ["silvaplana"],
                "spot_name": ["Silvaplana"],
                "requested_spot_ids": ["silvaplana"],
            }
        )

        # Build a fake observed DataFrame matching what fetch_archive returns.
        observed_index = pd.DatetimeIndex(
            [forecast_base],
            name="time",
        )
        observed_raw = pd.DataFrame(
            {
                "wind_speed_10m": [25.0],
                "wind_speed_80m": [30.0],
                "wind_gusts_10m": [30.0],
                "wind_direction_10m": [225.0],
                "temperature_2m": [15.0],
                "precipitation": [0.0],
                "relative_humidity_2m": [60.0],
                "cloud_cover": [20.0],
                "pressure_msl": [1015.0],
            },
            index=observed_index,
        )

        spots = [
            {
                "id": "silvaplana",
                "name": "Silvaplana",
                "lat": 46.45,
                "lon": 9.79,
                "shore_orientation_deg": 225,
            }
        ]

        with (
            patch(
                "foehncast.monitoring.hindcast.read_prediction_history",
                return_value=history,
            ),
            patch(
                "foehncast.monitoring.hindcast.fetch_archive",
                return_value=observed_raw,
            ),
            patch(
                "foehncast.monitoring.hindcast.get_spots",
                return_value=spots,
            ),
            patch(
                "foehncast.monitoring.hindcast.get_rider_config",
                return_value={
                    "weight_kg": 80,
                    "home_location": "Zurich",
                    "home_lat": 47.37,
                    "home_lon": 8.54,
                    "quiver_m2": [9, 12],
                },
            ),
            _NOOP_WRITE,
        ):
            result = run_hindcast_validation(buffer_hours=120)

        assert result["validated_count"] >= 1
        assert result["accuracy"] is not None
        assert 0.0 <= result["accuracy"] <= 1.0
        assert result["mae"] is not None
        assert result["mae"] >= 0.0

    def test_handles_archive_failure_gracefully(self) -> None:
        history = _make_prediction_history(forecast_hours_ago=200)
        spots = [
            {
                "id": "silvaplana",
                "name": "Silvaplana",
                "lat": 46.45,
                "lon": 9.79,
                "shore_orientation_deg": 225,
            }
        ]

        with (
            patch(
                "foehncast.monitoring.hindcast.read_prediction_history",
                return_value=history,
            ),
            patch(
                "foehncast.monitoring.hindcast.fetch_archive",
                side_effect=ConnectionError("API unavailable"),
            ),
            patch(
                "foehncast.monitoring.hindcast.get_spots",
                return_value=spots,
            ),
            patch(
                "foehncast.monitoring.hindcast.get_rider_config",
                return_value={"weight_kg": 80},
            ),
            _NOOP_WRITE,
        ):
            result = run_hindcast_validation(buffer_hours=120)

        assert result["validated_count"] == 0
        assert result["accuracy"] is None


class TestReadHindcastResult:
    def test_returns_empty_when_no_file(self, tmp_path: object) -> None:
        from pathlib import Path

        missing = Path(str(tmp_path)) / "missing.json"
        result = read_hindcast_result(missing)
        assert result["validated_count"] == 0
        assert result["accuracy"] is None

    def test_reads_persisted_result(self, tmp_path: object) -> None:
        import json
        from pathlib import Path

        state = Path(str(tmp_path)) / "hindcast-validation.json"
        state.write_text(
            json.dumps({"validated_count": 42, "accuracy": 0.85, "mae": 0.3})
        )
        result = read_hindcast_result(state)
        assert result["validated_count"] == 42
        assert result["accuracy"] == 0.85
