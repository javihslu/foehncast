"""Tests for the DVC stage entry points."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from foehncast import dvc_stages
from foehncast.feature_pipeline import engineer, ingest, validate


def _curated_feature_frame(rows: int = 10) -> pd.DataFrame:
    """Tiny curated frame with all model features plus labeling columns."""
    index = pd.date_range("2025-01-01T00:00:00", periods=rows, freq="h")
    wind = [[20.0, 30.0, 35.0, 45.0][i % 4] for i in range(rows)]
    return pd.DataFrame(
        {
            "wind_speed_10m": wind,
            "wind_speed_80m": [value + 2.0 for value in wind],
            "wind_gusts_10m": [value + 6.0 for value in wind],
            "temperature_2m": [10.0 + 0.5 * i for i in range(rows)],
            "relative_humidity_2m": [60.0 - i for i in range(rows)],
            "hour_of_day_sin": [0.05 * i for i in range(rows)],
            "hour_of_day_cos": [1.0 - 0.05 * i for i in range(rows)],
            "day_of_year_sin": [0.0] * rows,
            "day_of_year_cos": [1.0] * rows,
            "wind_direction_10m_sin": [-0.5] * rows,
            "wind_direction_10m_cos": [-0.85] * rows,
            "wind_steadiness": [0.10 + 0.01 * i for i in range(rows)],
            "gust_excess_10m": [6.0] * rows,
            "gust_factor": [1.2] * rows,
            "shore_alignment": [0.8] * rows,
        },
        index=index,
    )


def test_train_writes_metrics_report_and_feature_importance_plot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(dvc_stages, "_project_root", lambda: tmp_path)
    data_dir = tmp_path / "data" / "train"
    data_dir.mkdir(parents=True)

    frame = _curated_feature_frame()
    frame.loc[frame.index[-1], "wind_speed_10m"] = np.nan
    frame.to_parquet(data_dir / "silvaplana.parquet")

    dvc_stages.train("train")

    metrics = json.loads((tmp_path / "reports" / "train_metrics.json").read_text())
    assert {"mae", "rmse", "r2", "data_hash", "git_commit"} <= set(metrics)
    assert metrics["training_row_count"] == 9
    assert metrics["training_feature_count"] == 14
    assert (tmp_path / "reports" / "feature_importance.png").exists()


def test_curate_writes_parquet_for_valid_spot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(dvc_stages, "_project_root", lambda: tmp_path)
    forecast_df = pd.DataFrame(
        {"wind_speed_10m": [20.0, 30.0]},
        index=pd.date_range("2025-01-01T00:00:00", periods=2, freq="h"),
    )
    monkeypatch.setattr(ingest, "fetch_all_spots", lambda: {"silvaplana": forecast_df})
    monkeypatch.setattr(
        engineer,
        "engineer_features",
        lambda df, shore_orientation_deg: df.copy(),
    )
    monkeypatch.setattr(
        validate,
        "run_validation",
        lambda df, spot_id: SimpleNamespace(is_valid=True),
    )

    dvc_stages.curate("train")

    out_path = tmp_path / "data" / "train" / "silvaplana.parquet"
    assert out_path.exists()
    assert len(pd.read_parquet(out_path)) == 2


def test_curate_exits_when_no_spot_produces_valid_data(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(dvc_stages, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(ingest, "fetch_all_spots", lambda: {})

    with pytest.raises(SystemExit):
        dvc_stages.curate("train")
