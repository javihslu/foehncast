"""Tests for Feast export helpers."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from foehncast.feature_pipeline import feast


def test_to_feast_frame_uses_datetime_index() -> None:
    index = pd.date_range("2025-01-01T00:00:00", periods=2, freq="h")
    features_df = pd.DataFrame({"wind_speed_10m": [10.0, 12.0]}, index=index)

    result = feast._to_feast_frame(features_df, spot_id="silvaplana")

    assert list(result.columns) == ["event_timestamp", "wind_speed_10m", "spot_id"]
    assert result["spot_id"].tolist() == ["silvaplana", "silvaplana"]
    assert str(result["event_timestamp"].dtype).startswith("datetime64[ns, UTC]")


def test_build_offline_store_frame_combines_spots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = pd.date_range("2025-01-01T00:00:00", periods=2, freq="h")
    silvaplana = pd.DataFrame({"wind_speed_10m": [10.0, 12.0]}, index=index)
    urnersee = pd.DataFrame({"wind_speed_10m": [14.0, 16.0]}, index=index)

    monkeypatch.setattr(
        feast,
        "get_spots",
        lambda: [{"id": "silvaplana"}, {"id": "urnersee"}, {"id": "missing"}],
    )

    def _read_features(spot_id: str, dataset: str) -> pd.DataFrame:
        if spot_id == "silvaplana":
            return silvaplana
        if spot_id == "urnersee":
            return urnersee
        raise FileNotFoundError(spot_id)

    monkeypatch.setattr(feast, "read_features", _read_features)

    result = feast.build_offline_store_frame(dataset="train")

    assert result["spot_id"].tolist() == [
        "silvaplana",
        "urnersee",
        "silvaplana",
        "urnersee",
    ]
    assert "event_timestamp" in result.columns
    assert len(result) == 4


def test_export_offline_store_writes_parquet(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    frame = pd.DataFrame(
        {
            "spot_id": ["silvaplana"],
            "event_timestamp": pd.to_datetime(["2025-01-01T00:00:00Z"]),
            "wind_speed_10m": [12.0],
        }
    )
    monkeypatch.setattr(feast, "build_offline_store_frame", lambda dataset: frame)

    destination = feast.export_offline_store(
        dataset="train", output_path=tmp_path / "feast" / "train.parquet"
    )

    result = pd.read_parquet(destination)
    pd.testing.assert_frame_equal(result, frame)
