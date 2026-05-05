"""Tests for feature-pipeline data validation."""

from __future__ import annotations

import pandas as pd

from foehncast.feature_pipeline.validate import (
    ValidationResult,
    run_validation,
    validate_completeness,
    validate_ranges,
    validate_schema,
)


def _sample_raw_features() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "wind_speed_10m": [12.0, 18.0],
            "wind_speed_80m": [15.0, 20.0],
            "wind_speed_120m": [18.0, 22.0],
            "wind_direction_10m": [220.0, 235.0],
            "wind_direction_80m": [225.0, 240.0],
            "wind_gusts_10m": [18.0, 24.0],
            "temperature_2m": [12.0, 14.0],
            "precipitation": [0.0, 0.2],
            "relative_humidity_2m": [55.0, 60.0],
            "cloud_cover": [25.0, 40.0],
            "pressure_msl": [1013.0, 1012.0],
            "cape": [50.0, 75.0],
            "lifted_index": [-1.0, -2.0],
        },
        index=pd.Index(["row-1", "row-2"], name="time"),
    )


def _sample_curated_features() -> pd.DataFrame:
    df = _sample_raw_features().copy()
    df["hour_of_day_sin"] = [0.0, 0.258819]
    df["hour_of_day_cos"] = [1.0, 0.965926]
    df["day_of_year_sin"] = [0.845249, 0.845249]
    df["day_of_year_cos"] = [-0.534373, -0.534373]
    df["wind_steadiness"] = [0.0, 0.052632]
    df["gust_factor"] = [1.50, 1.33]
    df["shore_alignment"] = [0.85, 0.88]
    return df


def test_validate_schema_returns_true_when_all_columns_are_present() -> None:
    df = _sample_raw_features()

    assert validate_schema(df, ["wind_speed_10m", "temperature_2m"])


def test_validate_schema_returns_false_when_columns_are_missing() -> None:
    df = _sample_raw_features().drop(columns=["temperature_2m"])

    assert not validate_schema(df, ["wind_speed_10m", "temperature_2m"])


def test_validate_ranges_returns_violation_rows() -> None:
    df = _sample_raw_features()
    df.loc["row-2", "wind_direction_10m"] = 400.0
    df.loc["row-1", "temperature_2m"] = -45.0

    violations = validate_ranges(
        df,
        {
            "wind_direction_10m": {"min": 0, "max": 360},
            "temperature_2m": {"min": -40, "max": 50},
        },
    )

    assert list(violations["column"]) == ["wind_direction_10m", "temperature_2m"]
    assert list(violations["index"]) == ["row-2", "row-1"]


def test_validate_completeness_fails_when_column_exceeds_null_threshold() -> None:
    df = _sample_raw_features()
    df["temperature_2m"] = [None, 14.0]

    assert not validate_completeness(df, max_null_pct=0.4)


def test_run_validation_returns_valid_result_for_clean_dataset(monkeypatch) -> None:
    df = _sample_curated_features()
    monkeypatch.setattr(
        "foehncast.feature_pipeline.validate.get_validation_config",
        lambda: {
            "required_columns": list(df.columns),
            "completeness": {"max_null_pct": 0.1},
            "ranges": {
                "wind_speed_10m": {"min": 0, "max": 80},
                "wind_gusts_10m": {"min": 0, "max": 120},
                "wind_direction_10m": {"min": 0, "max": 360},
                "temperature_2m": {"min": -40, "max": 50},
                "relative_humidity_2m": {"min": 0, "max": 100},
                "hour_of_day_sin": {"min": -1, "max": 1},
                "hour_of_day_cos": {"min": -1, "max": 1},
                "day_of_year_sin": {"min": -1, "max": 1},
                "day_of_year_cos": {"min": -1, "max": 1},
                "wind_steadiness": {"min": 0},
                "gust_factor": {"min": 0},
                "shore_alignment": {"min": -1, "max": 1},
            },
        },
    )

    result = run_validation(df, spot_id="silvaplana")

    assert isinstance(result, ValidationResult)
    assert result.spot_id == "silvaplana"
    assert result.is_valid
    assert result.range_violations.empty
    assert result.missing_columns == []


def test_run_validation_collects_missing_columns_and_range_violations(
    monkeypatch,
) -> None:
    df = _sample_curated_features().drop(columns=["shore_alignment"])
    df.loc["row-2", "hour_of_day_sin"] = 1.2
    monkeypatch.setattr(
        "foehncast.feature_pipeline.validate.get_validation_config",
        lambda: {
            "required_columns": [*list(_sample_curated_features().columns)],
            "completeness": {"max_null_pct": 0.1},
            "ranges": {
                "hour_of_day_sin": {"min": -1, "max": 1},
                "shore_alignment": {"min": -1, "max": 1},
            },
        },
    )

    result = run_validation(df, spot_id="urnersee")

    assert not result.is_valid
    assert not result.schema_valid
    assert result.completeness_valid
    assert not result.range_valid
    assert result.missing_columns == ["shore_alignment"]
    assert list(result.range_violations["column"]) == ["hour_of_day_sin"]
