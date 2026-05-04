"""Feast feature definitions for curated FoehnCast weather features."""

from __future__ import annotations

import os
from datetime import timedelta

from feast import Entity, FeatureService, FeatureView, Field, FileSource
from feast.types import Float64
from feast.value_type import ValueType

_SOURCE_MODE = os.getenv("FOEHNCAST_FEAST_SOURCE", "local").strip().lower()
_LOCAL_FILE_PATH = os.getenv("FOEHNCAST_FEAST_FILE_PATH", "../data/feast/train.parquet")
_BIGQUERY_TABLE = os.getenv("FOEHNCAST_FEAST_BIGQUERY_TABLE", "").strip()


def _build_source():
    if _SOURCE_MODE == "local":
        return FileSource(
            path=_LOCAL_FILE_PATH,
            event_timestamp_column="event_timestamp",
        )

    if _SOURCE_MODE == "bigquery":
        if not _BIGQUERY_TABLE:
            raise ValueError(
                "FOEHNCAST_FEAST_BIGQUERY_TABLE must be set when using BigQuery as the Feast source"
            )

        from feast.infra.offline_stores.bigquery_source import BigQuerySource

        return BigQuerySource(
            table=_BIGQUERY_TABLE,
            timestamp_field="forecast_time",
        )

    raise ValueError(f"Unsupported FOEHNCAST_FEAST_SOURCE: {_SOURCE_MODE}")


spot = Entity(name="spot_id", join_keys=["spot_id"], value_type=ValueType.STRING)

spot_forecast_source = _build_source()

spot_forecast_features = FeatureView(
    name="spot_forecast_features",
    entities=[spot],
    ttl=timedelta(days=8),
    schema=[
        Field(name="wind_speed_10m", dtype=Float64),
        Field(name="wind_speed_80m", dtype=Float64),
        Field(name="wind_speed_120m", dtype=Float64),
        Field(name="wind_direction_10m", dtype=Float64),
        Field(name="wind_direction_80m", dtype=Float64),
        Field(name="wind_gusts_10m", dtype=Float64),
        Field(name="temperature_2m", dtype=Float64),
        Field(name="precipitation", dtype=Float64),
        Field(name="relative_humidity_2m", dtype=Float64),
        Field(name="cloud_cover", dtype=Float64),
        Field(name="pressure_msl", dtype=Float64),
        Field(name="cape", dtype=Float64),
        Field(name="lifted_index", dtype=Float64),
        Field(name="hour_of_day_sin", dtype=Float64),
        Field(name="hour_of_day_cos", dtype=Float64),
        Field(name="day_of_year_sin", dtype=Float64),
        Field(name="day_of_year_cos", dtype=Float64),
        Field(name="wind_steadiness", dtype=Float64),
        Field(name="gust_factor", dtype=Float64),
        Field(name="shore_alignment", dtype=Float64),
    ],
    source=spot_forecast_source,
    online=True,
)

foehncast_model_v1 = FeatureService(
    name="foehncast_model_v1",
    features=[spot_forecast_features],
)
