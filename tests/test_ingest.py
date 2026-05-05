"""Tests for data ingestion from weather APIs."""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from foehncast.feature_pipeline.ingest import (
    _hourly_to_dataframe,
    fetch_archive,
    fetch_forecast,
    fetch_spot,
)

# --- Fixtures ---

MOCK_HOURLY_RESPONSE = {
    "hourly": {
        "time": ["2026-04-12T00:00", "2026-04-12T01:00", "2026-04-12T02:00"],
        "wind_speed_10m": [15.2, 16.8, 14.5],
        "wind_gusts_10m": [22.1, 24.3, 20.0],
        "wind_direction_10m": [220, 225, 215],
        "temperature_2m": [12.0, 11.5, 11.0],
    },
    "hourly_units": {
        "time": "iso8601",
        "wind_speed_10m": "km/h",
        "wind_gusts_10m": "km/h",
        "wind_direction_10m": "°",
        "temperature_2m": "°C",
    },
}

MOCK_SPOT = {
    "id": "silvaplana",
    "name": "Silvaplana",
    "lat": 46.45,
    "lon": 9.79,
}


# --- Unit tests ---


class TestHourlyToDataframe:
    def test_converts_valid_response(self) -> None:
        df = _hourly_to_dataframe(MOCK_HOURLY_RESPONSE, timezone="Europe/Zurich")
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 3
        assert "wind_speed_10m" in df.columns
        assert df.index.name == "time"

    def test_returns_empty_for_missing_hourly(self) -> None:
        df = _hourly_to_dataframe({})
        assert df.empty

    def test_parses_timestamps(self) -> None:
        df = _hourly_to_dataframe(MOCK_HOURLY_RESPONSE, timezone="Europe/Zurich")
        assert pd.api.types.is_datetime64_any_dtype(df.index)

    def test_localizes_timestamps_to_configured_timezone(self) -> None:
        df = _hourly_to_dataframe(MOCK_HOURLY_RESPONSE, timezone="Europe/Zurich")
        assert str(df.index.tz) == "Europe/Zurich"

    def test_preserves_hourly_units_in_dataframe_attrs(self) -> None:
        df = _hourly_to_dataframe(MOCK_HOURLY_RESPONSE, timezone="Europe/Zurich")
        assert df.attrs["hourly_units"]["wind_speed_10m"] == "km/h"
        assert df.attrs["hourly_units"]["wind_gusts_10m"] == "km/h"

    def test_rejects_unexpected_wind_units(self) -> None:
        response = {
            **MOCK_HOURLY_RESPONSE,
            "hourly_units": {
                **MOCK_HOURLY_RESPONSE["hourly_units"],
                "wind_speed_10m": "kn",
            },
        }

        with pytest.raises(ValueError, match="Unexpected unit for wind_speed_10m"):
            _hourly_to_dataframe(response, timezone="Europe/Zurich")


class TestFetchForecast:
    @patch("foehncast.feature_pipeline.ingest._get")
    def test_returns_dataframe(self, mock_get) -> None:
        mock_get.return_value = MOCK_HOURLY_RESPONSE
        df = fetch_forecast(46.45, 9.79)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 3
        assert str(df.index.tz) == "Europe/Zurich"
        mock_get.assert_called_once()

    @patch("foehncast.feature_pipeline.ingest._get")
    def test_passes_correct_params(self, mock_get) -> None:
        mock_get.return_value = MOCK_HOURLY_RESPONSE
        fetch_forecast(46.45, 9.79)
        _, kwargs = mock_get.call_args
        params = kwargs["params"] if "params" in kwargs else mock_get.call_args[0][1]
        assert params["latitude"] == 46.45
        assert params["longitude"] == 9.79
        assert params["wind_speed_unit"] == "kmh"


class TestFetchArchive:
    @patch("foehncast.feature_pipeline.ingest._get")
    def test_returns_dataframe(self, mock_get) -> None:
        mock_get.return_value = MOCK_HOURLY_RESPONSE
        df = fetch_archive(46.45, 9.79, "2024-01-01", "2024-01-31")
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 3
        assert str(df.index.tz) == "Europe/Zurich"

    @patch("foehncast.feature_pipeline.ingest._get")
    def test_passes_explicit_wind_speed_unit(self, mock_get) -> None:
        mock_get.return_value = MOCK_HOURLY_RESPONSE
        fetch_archive(46.45, 9.79, "2024-01-01", "2024-01-31")
        _, kwargs = mock_get.call_args
        params = kwargs["params"] if "params" in kwargs else mock_get.call_args[0][1]
        assert params["wind_speed_unit"] == "kmh"


class TestFetchSpot:
    @patch("foehncast.feature_pipeline.ingest.fetch_forecast")
    def test_adds_spot_metadata(self, mock_fetch) -> None:
        mock_fetch.return_value = pd.DataFrame(
            {"wind_speed_10m": [15.0]},
            index=pd.to_datetime(["2026-04-12T00:00"]),
        )
        mock_fetch.return_value.index.name = "time"
        df = fetch_spot(MOCK_SPOT)
        assert df["spot_id"].iloc[0] == "silvaplana"
        assert df["spot_name"].iloc[0] == "Silvaplana"

    @patch("foehncast.feature_pipeline.ingest.fetch_forecast")
    def test_returns_empty_for_empty_response(self, mock_fetch) -> None:
        mock_fetch.return_value = pd.DataFrame()
        df = fetch_spot(MOCK_SPOT)
        assert df.empty
