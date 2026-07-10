"""Tests for Feast online feature helpers."""

from __future__ import annotations

import builtins
from pathlib import Path
import sys
from types import ModuleType

import pytest

from foehncast.inference_pipeline import online_features


def test_load_feature_store_raises_runtime_error_when_feast_dependency_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_import = builtins.__import__

    def fake_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "feast":
            raise ModuleNotFoundError("No module named 'feast'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(
        RuntimeError,
        match="Feast runtime dependency is missing from this environment",
    ):
        online_features._load_feature_store()


def test_get_online_spot_features_uses_feature_service(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    logged: dict[str, object] = {}
    repo_path = tmp_path / "feature_repo"
    repo_path.mkdir()

    class FakeResponse:
        def to_dict(self) -> dict[str, list[object]]:
            return {
                "spot_id": ["silvaplana", "urnersee"],
                "wind_speed_10m": [14.0, 16.0],
                "gust_excess_10m": [4.0, 5.0],
            }

    class FakeStore:
        def __init__(self, repo_path: str, fs_yaml_file) -> None:
            logged["repo_path"] = repo_path
            logged["fs_yaml_file"] = Path(fs_yaml_file)

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
    monkeypatch.setenv("FOEHNCAST_FEAST_REPO_PATH", str(repo_path))
    monkeypatch.setattr(
        online_features,
        "_resolve_spots",
        lambda spot_ids: [{"id": "silvaplana"}, {"id": "urnersee"}],
    )

    result = online_features.get_online_spot_features()

    assert logged["repo_path"] == str(repo_path)
    assert (
        logged["fs_yaml_file"]
        == tmp_path / ".state" / "feast" / "feature_store.runtime.yaml"
    )
    assert logged["feature_service"] == "foehncast_model_v1"
    assert logged["features"] == "service:foehncast_model_v1"
    assert logged["entity_rows"] == [
        {"spot_id": "silvaplana"},
        {"spot_id": "urnersee"},
    ]
    assert result == {
        "feature_service": "foehncast_model_v1",
        "returned_features": ["wind_speed_10m", "gust_excess_10m"],
        "rows": [
            {
                "spot_id": "silvaplana",
                "wind_speed_10m": 14.0,
                "gust_excess_10m": 4.0,
            },
            {
                "spot_id": "urnersee",
                "wind_speed_10m": 16.0,
                "gust_excess_10m": 5.0,
            },
        ],
    }


def test_get_online_spot_features_prefixes_unqualified_feature_names(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    logged: dict[str, object] = {}
    repo_path = tmp_path / "feature_repo"
    repo_path.mkdir()

    class FakeResponse:
        def to_dict(self) -> dict[str, list[object]]:
            return {
                "spot_id": ["silvaplana"],
                "wind_speed_10m": [14.0],
                "gust_excess_10m": [4.0],
            }

    class FakeStore:
        def __init__(self, repo_path: str, fs_yaml_file) -> None:
            logged["repo_path"] = repo_path
            logged["fs_yaml_file"] = Path(fs_yaml_file)

        def get_online_features(
            self, *, features: object, entity_rows: list[dict[str, str]]
        ) -> FakeResponse:
            logged["features"] = features
            logged["entity_rows"] = entity_rows
            return FakeResponse()

    fake_feast = ModuleType("feast")
    fake_feast.FeatureStore = FakeStore

    monkeypatch.setitem(sys.modules, "feast", fake_feast)
    monkeypatch.setenv("FOEHNCAST_FEAST_REPO_PATH", str(repo_path))
    monkeypatch.setattr(
        online_features,
        "_resolve_spots",
        lambda spot_ids: [{"id": "silvaplana"}],
    )

    result = online_features.get_online_spot_features(
        ["silvaplana"],
        ["wind_speed_10m", "spot_forecast_features:gust_excess_10m"],
    )

    assert logged["features"] == [
        "spot_forecast_features:wind_speed_10m",
        "spot_forecast_features:gust_excess_10m",
    ]
    assert (
        logged["fs_yaml_file"]
        == tmp_path / ".state" / "feast" / "feature_store.runtime.yaml"
    )
    assert logged["entity_rows"] == [{"spot_id": "silvaplana"}]
    assert result["feature_service"] is None
    assert result["rows"] == [
        {
            "spot_id": "silvaplana",
            "wind_speed_10m": 14.0,
            "gust_excess_10m": 4.0,
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

    with pytest.raises(RuntimeError, match="Configured Feast repo not found"):
        online_features.get_online_spot_features(["silvaplana"])
