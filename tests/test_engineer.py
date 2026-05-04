"""Tests for feature engineering functions."""

import pandas as pd
import pytest

from foehncast.feature_pipeline.engineer import (
    engineer_features,
    gust_factor,
    shore_alignment,
    wind_steadiness,
)


@pytest.fixture()
def sample_df():
    """Minimal hourly forecast DataFrame for testing."""
    index = pd.date_range("2025-01-01T00:00:00", periods=5, freq="h")
    return pd.DataFrame(
        {
            "wind_speed_10m": [10.0, 12.0, 14.0, 11.0, 13.0],
            "wind_gusts_10m": [15.0, 18.0, 20.0, 14.0, 19.0],
            "wind_direction_10m": [180.0, 190.0, 200.0, 185.0, 195.0],
        },
        index=index,
    )


class TestWindSteadiness:
    def test_returns_series(self, sample_df):
        result = wind_steadiness(sample_df)
        assert isinstance(result, pd.Series)
        assert len(result) == len(sample_df)

    def test_constant_wind_has_zero_cv(self):
        df = pd.DataFrame({"wind_speed_10m": [10.0, 10.0, 10.0]})
        result = wind_steadiness(df, window=3)
        assert result.iloc[-1] == pytest.approx(0.0)

    def test_zero_wind_returns_nan(self):
        df = pd.DataFrame({"wind_speed_10m": [0.0, 0.0, 0.0]})
        result = wind_steadiness(df, window=3)
        assert result.isna().all()


class TestGustFactor:
    def test_returns_ratio(self, sample_df):
        result = gust_factor(sample_df)
        expected = sample_df["wind_gusts_10m"] / sample_df["wind_speed_10m"]
        pd.testing.assert_series_equal(result, expected)

    def test_zero_wind_returns_nan(self):
        df = pd.DataFrame({"wind_gusts_10m": [5.0], "wind_speed_10m": [0.0]})
        result = gust_factor(df)
        assert result.isna().all()


class TestShoreAlignment:
    def test_perpendicular_scores_one(self):
        """Wind matching shore orientation → cos(0) = 1.0."""
        df = pd.DataFrame({"wind_direction_10m": [180.0]})
        result = shore_alignment(df, shore_orientation_deg=180.0)
        assert result.iloc[0] == pytest.approx(1.0)

    def test_opposite_scores_negative_one(self):
        """Wind 180° off shore orientation → cos(π) = -1.0."""
        df = pd.DataFrame({"wind_direction_10m": [0.0]})
        result = shore_alignment(df, shore_orientation_deg=180.0)
        assert result.iloc[0] == pytest.approx(-1.0)

    def test_ninety_degrees_scores_zero(self):
        """Wind 90° off shore orientation → cos(π/2) ≈ 0.0."""
        df = pd.DataFrame({"wind_direction_10m": [270.0]})
        result = shore_alignment(df, shore_orientation_deg=180.0)
        assert result.iloc[0] == pytest.approx(0.0, abs=1e-10)


class TestEngineerFeatures:
    def test_adds_all_columns(self, sample_df):
        result = engineer_features(sample_df, shore_orientation_deg=225.0)
        assert "hour_of_day_sin" in result.columns
        assert "hour_of_day_cos" in result.columns
        assert "day_of_year_sin" in result.columns
        assert "day_of_year_cos" in result.columns
        assert "wind_steadiness" in result.columns
        assert "gust_factor" in result.columns
        assert "shore_alignment" in result.columns

    def test_adds_expected_cyclical_values(self, sample_df):
        result = engineer_features(sample_df, shore_orientation_deg=225.0)

        assert result.iloc[0]["hour_of_day_sin"] == pytest.approx(0.0)
        assert result.iloc[0]["hour_of_day_cos"] == pytest.approx(1.0)
        assert result.iloc[0]["day_of_year_sin"] == pytest.approx(0.0)
        assert result.iloc[0]["day_of_year_cos"] == pytest.approx(1.0)

    def test_preserves_original_columns(self, sample_df):
        result = engineer_features(sample_df, shore_orientation_deg=225.0)
        for col in sample_df.columns:
            assert col in result.columns

    def test_does_not_mutate_input(self, sample_df):
        original = sample_df.copy()
        engineer_features(sample_df, shore_orientation_deg=225.0)
        pd.testing.assert_frame_equal(sample_df, original)
