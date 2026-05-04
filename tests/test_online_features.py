"""Tests for optional Feast online feature helpers."""

from __future__ import annotations

import sys
from types import ModuleType

import pytest

from foehncast.inference_pipeline import online_features


def test_get_online_spot_features_uses_feature_service(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    logged: dict[str, object] = {}

    class FakeResponse:
        def to_dict(self) -> dict[str, list[object]]:
            return {
                "spot_id": ["silvaplana", "urnersee"],
                "wind_speed_10m": [14.0, 16.0],
                "gust_factor": [1.5, 1.7],
            }

    class FakeStore:
        def __init__(self, repo_path: str) -> None:
            logged["repo_path"] = repo_path

        def get_feature_service(self, name: str) -> str:
            logged["feature_service"] = name
            return f"service:{name}"

        def get_online_features(
            self, *, features: object, entity_rows: list[dict[str, str]]
        ) -> FakeResponse:
            logged["features"] = features
            logged["entity_rows"] = entity_rows
            return FakeResponse()

    fake_feast = ModuleType("feast")
    fake_feast.FeatureStore = FakeStore

    monkeypatch.setitem(sys.modules, "feast", fake_feast)
    monkeypatch.setenv("FOEHNCAST_FEAST_REPO_PATH", str(tmp_path))
    monkeypatch.setattr(
        online_features,
        "_resolve_spots",
        lambda spot_ids: [{"id": "silvaplana"}, {"id": "urnersee"}],
    )

    result = online_features.get_online_spot_features()

    assert logged["repo_path"] == str(tmp_path)
    assert logged["feature_service"] == "foehncast_model_v1"
    assert logged["features"] == "service:foehncast_model_v1"
    assert logged["entity_rows"] == [
        {"spot_id": "silvaplana"},
        {"spot_id": "urnersee"},
    ]
    assert result == {
        "feature_service": "foehncast_model_v1",
        "returned_features": ["wind_speed_10m", "gust_factor"],
        "rows": [
            {
                "spot_id": "silvaplana",
                "wind_speed_10m": 14.0,
                "gust_factor": 1.5,
            },
            {
                "spot_id": "urnersee",
                "wind_speed_10m": 16.0,
                "gust_factor": 1.7,
            },
        ],
    }


def test_get_online_spot_features_prefixes_unqualified_feature_names(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    logged: dict[str, object] = {}

    class FakeResponse:
        def to_dict(self) -> dict[str, list[object]]:
            return {
                "spot_id": ["silvaplana"],
                "wind_speed_10m": [14.0],
                "gust_factor": [1.5],
            }

    class FakeStore:
        def __init__(self, repo_path: str) -> None:
            logged["repo_path"] = repo_path

        def get_online_features(
            self, *, features: object, entity_rows: list[dict[str, str]]
        ) -> FakeResponse:
            logged["features"] = features
            logged["entity_rows"] = entity_rows
            return FakeResponse()

    fake_feast = ModuleType("feast")
    fake_feast.FeatureStore = FakeStore

    monkeypatch.setitem(sys.modules, "feast", fake_feast)
    monkeypatch.setenv("FOEHNCAST_FEAST_REPO_PATH", str(tmp_path))
    monkeypatch.setattr(
        online_features,
        "_resolve_spots",
        lambda spot_ids: [{"id": "silvaplana"}],
    )

    result = online_features.get_online_spot_features(
        ["silvaplana"],
        ["wind_speed_10m", "spot_forecast_features:gust_factor"],
    )

    assert logged["features"] == [
        "spot_forecast_features:wind_speed_10m",
        "spot_forecast_features:gust_factor",
    ]
    assert logged["entity_rows"] == [{"spot_id": "silvaplana"}]
    assert result["feature_service"] is None
    assert result["rows"] == [
        {
            "spot_id": "silvaplana",
            "wind_speed_10m": 14.0,
            "gust_factor": 1.5,
        }
    ]


def test_get_online_spot_features_requires_existing_repo(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    fake_feast = ModuleType("feast")
    fake_feast.FeatureStore = object

    monkeypatch.setitem(sys.modules, "feast", fake_feast)
    monkeypatch.setenv("FOEHNCAST_FEAST_REPO_PATH", str(tmp_path / "missing"))
    monkeypatch.setattr(
        online_features,
        "_resolve_spots",
        lambda spot_ids: [{"id": "silvaplana"}],
    )

    with pytest.raises(RuntimeError, match="Feast repo not found"):
        online_features.get_online_spot_features(["silvaplana"])
