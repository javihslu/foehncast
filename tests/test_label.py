"""Tests for synthetic label generation from physics rules."""

import pandas as pd
import pytest

from foehncast.training_pipeline.label import compute_quality_index, label_dataset


@pytest.fixture()
def labeled_features_df() -> pd.DataFrame:
    """Feature rows that should hit each quality bucket."""
    return pd.DataFrame(
        {
            "wind_speed_10m": [45.0, 10.0, 16.0, 19.0, 26.0, 20.0],
            "wind_gusts_10m": [46.0, 12.0, 18.0, 21.0, 28.0, 22.0],
            "wind_steadiness": [0.10, 0.30, 0.25, 0.22, 0.18, 0.15],
            "gust_factor": [1.02, 1.20, 1.12, 1.10, 1.08, 1.10],
            "shore_alignment": [0.90, 0.10, 0.20, 0.30, 0.60, 0.85],
        }
    )


class TestComputeQualityIndex:
    def test_assigns_expected_quality_buckets(self, labeled_features_df: pd.DataFrame):
        rider_config = {"weight_kg": 80}

        result = compute_quality_index(labeled_features_df, rider_config)

        assert result.tolist() == [0, 1, 2, 3, 4, 5]

    def test_light_rider_uses_lower_minimum_wind_threshold(self):
        features_df = pd.DataFrame(
            {
                "wind_speed_10m": [13.0],
                "wind_gusts_10m": [15.0],
                "wind_steadiness": [0.25],
                "gust_factor": [1.15],
                "shore_alignment": [0.20],
            }
        )

        light_rider = {"weight_kg": 70}
        heavy_rider = {"weight_kg": 80}

        assert compute_quality_index(features_df, light_rider).iloc[0] == 2
        assert compute_quality_index(features_df, heavy_rider).iloc[0] == 1

    def test_missing_required_columns_raises_key_error(self):
        features_df = pd.DataFrame({"wind_speed_10m": [20.0]})

        with pytest.raises(KeyError, match="Missing required columns"):
            compute_quality_index(features_df, {"weight_kg": 80})


class TestLabelDataset:
    def test_adds_quality_index_without_mutating_input(
        self, labeled_features_df: pd.DataFrame
    ):
        original = labeled_features_df.copy()

        result = label_dataset(labeled_features_df, {"weight_kg": 80})

        assert "quality_index" in result.columns
        assert result["quality_index"].tolist() == [0, 1, 2, 3, 4, 5]
        pd.testing.assert_frame_equal(labeled_features_df, original)
