"""Tests for the recent-hours option of the history backfill script."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "backfill_history", REPO_ROOT / "scripts" / "backfill-history.py"
)
backfill_history = importlib.util.module_from_spec(_spec)
sys.modules["backfill_history"] = backfill_history
_spec.loader.exec_module(backfill_history)

SPOT = {"id": "silvaplana", "lat": 46.45, "lon": 9.79, "shore_orientation_deg": 45}


def test_fetch_spot_recent_asks_for_past_days_and_drops_future_hours(
    monkeypatch,
) -> None:
    now = pd.Timestamp.now(tz="UTC").floor("h")
    raw = pd.DataFrame(
        {"wind_speed_10m": [1.0, 2.0, 3.0, 4.0]},
        index=pd.date_range(now - pd.Timedelta(hours=2), periods=4, freq="h"),
    )
    calls = {}

    def fake_fetch_forecast(lat, lon, *, past_days=0, forecast_hours=None):
        calls["args"] = (lat, lon, past_days)
        return raw

    engineered = {}

    def fake_engineer_features(df, shore_orientation_deg):
        engineered["index"] = df.index
        return df

    monkeypatch.setattr(backfill_history, "fetch_forecast", fake_fetch_forecast)
    monkeypatch.setattr(backfill_history, "engineer_features", fake_engineer_features)
    monkeypatch.setattr(
        backfill_history,
        "run_validation",
        lambda df, spot_id: SimpleNamespace(is_valid=True),
    )

    out = backfill_history._fetch_spot_recent(SPOT, 2)

    assert calls["args"] == (SPOT["lat"], SPOT["lon"], 2)
    # The current hour and everything after it has not happened yet.
    assert list(engineered["index"]) == list(raw.index[:2])
    assert out.index.max() < now


def test_merge_curated_prefers_the_archive_row_and_its_columns() -> None:
    index = pd.date_range("2026-01-01", periods=3, freq="h", tz="UTC")
    archive = pd.DataFrame({"a": [1.0, 2.0], "b": [10.0, 20.0]}, index=index[:2])
    recent = pd.DataFrame({"b": [99.0, 30.0], "a": [99.0, 3.0]}, index=index[1:])

    merged = backfill_history._merge_curated(archive, recent)

    assert list(merged.columns) == ["a", "b"]
    assert list(merged.index) == list(index)
    # The overlapping hour keeps the archive's analysed values.
    assert merged.loc[index[1], "a"] == 2.0
    assert merged.loc[index[2], "a"] == 3.0
    assert backfill_history._merge_curated(None, None) is None


def test_cli_exposes_recent_days_defaulting_to_zero(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["backfill-history.py"])
    assert backfill_history._parse_args().recent_days == 0

    monkeypatch.setattr(sys, "argv", ["backfill-history.py", "--recent-days", "2"])
    assert backfill_history._parse_args().recent_days == 2


def test_objectstore_credentials_default_into_aws_env(monkeypatch) -> None:
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.setenv("OBJECTSTORE_ACCESS_KEY", "objkey")
    # An explicit AWS value must never be overwritten.
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "explicit")
    monkeypatch.setenv("OBJECTSTORE_SECRET_KEY", "objsecret")
    backfill_history._default_objectstore_credentials()
    assert os.environ["AWS_ACCESS_KEY_ID"] == "objkey"
    assert os.environ["AWS_SECRET_ACCESS_KEY"] == "explicit"
