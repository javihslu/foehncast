"""Feature pipeline observability helpers."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import mlflow
import pandas as pd

_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_REPORT_DIR = _ROOT / "airflow" / "reports"

FEATURE_PIPELINE_METRIC_CONTRACT: dict[str, tuple[str, ...]] = {
    "run": (
        "run_status",
        "dataset",
        "storage_backend",
        "expected_spot_count",
        "fetched_spot_count",
        "stored_spot_count",
        "skipped_spot_count",
        "failed_spot_count",
    ),
    "ingest": (
        "rows",
        "column_count",
        "time_start",
        "time_end",
        "timezone",
        "wind_speed_10m_unit",
        "wind_gusts_10m_unit",
        "source_unit_contract_confirmed",
        "hourly_units",
    ),
    "engineering": (
        "rows",
        "raw_column_count",
        "column_count",
        "engineered_column_count",
        "new_columns",
    ),
    "validation": (
        "is_valid",
        "missing_column_count",
        "missing_columns",
        "max_null_fraction",
        "range_violation_count",
    ),
    "storage": (
        "stored_rows",
        "stored_column_count",
        "missing_after_roundtrip_count",
        "extra_after_roundtrip_count",
        "max_numeric_abs_delta",
        "time_basis_preserved",
    ),
    "feast": (
        "projection_ready",
        "event_timestamp_source",
        "entity_key_ready",
    ),
}


def feature_pipeline_summary_path(dataset: str = "train") -> Path:
    """Return the stable JSON summary path for the latest feature pipeline run."""
    return _DEFAULT_REPORT_DIR / f"feature-pipeline-{dataset}-latest.json"


def feature_pipeline_summary_paths() -> list[Path]:
    """Return all persisted feature-pipeline summary paths."""
    return sorted(_DEFAULT_REPORT_DIR.glob("feature-pipeline-*-latest.json"))


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    numeric = float(value)
    if pd.isna(numeric):
        return None
    return numeric


def _iso_timestamp(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    return pd.Timestamp(value).isoformat()


def _timestamp_series(df: pd.DataFrame) -> pd.Series | None:
    if isinstance(df.index, pd.DatetimeIndex):
        return pd.Series(df.index, copy=False)
    if "time" in df.columns:
        return pd.Series(pd.to_datetime(df["time"]), copy=False)
    return None


def _time_window(df: pd.DataFrame) -> tuple[str | None, str | None, str | None]:
    timestamps = _timestamp_series(df)
    if timestamps is None or timestamps.empty:
        return None, None, None

    timezone = timestamps.dt.tz
    timezone_name = str(timezone) if timezone is not None else None
    return (
        _iso_timestamp(timestamps.min()),
        _iso_timestamp(timestamps.max()),
        timezone_name,
    )


def _hourly_units(df: pd.DataFrame) -> dict[str, str]:
    units = df.attrs.get("hourly_units", {}) if hasattr(df, "attrs") else {}
    return {str(key): str(value) for key, value in dict(units).items()}


def _max_null_fraction(null_fractions: dict[str, float]) -> float:
    if not null_fractions:
        return 0.0
    return float(max(null_fractions.values(), default=0.0))


def _range_violation_count(range_violations: Any) -> int:
    if isinstance(range_violations, pd.DataFrame):
        return int(len(range_violations))
    if range_violations is None:
        return 0
    return int(len(range_violations))


def _event_timestamp_source(df: pd.DataFrame) -> str | None:
    if isinstance(df.index, pd.DatetimeIndex):
        return "datetime_index"
    if "time" in df.columns:
        return "time_column"
    return None


def _time_basis_preserved(feature_df: pd.DataFrame, stored_df: pd.DataFrame) -> bool:
    if feature_df.empty or stored_df.empty:
        return False

    if isinstance(feature_df.index, pd.DatetimeIndex):
        return isinstance(stored_df.index, pd.DatetimeIndex)

    return "time" in feature_df.columns and "time" in stored_df.columns


def _max_numeric_abs_delta(
    feature_df: pd.DataFrame, stored_df: pd.DataFrame
) -> float | None:
    if feature_df.empty or stored_df.empty or len(feature_df) != len(stored_df):
        return None

    numeric_columns = [
        column
        for column in feature_df.columns
        if column in stored_df.columns
        and pd.api.types.is_numeric_dtype(feature_df[column])
        and pd.api.types.is_numeric_dtype(stored_df[column])
    ]
    if not numeric_columns:
        return None

    left = feature_df[numeric_columns].reset_index(drop=True)
    right = stored_df[numeric_columns].reset_index(drop=True)
    delta = (left - right).abs().max().max()
    return _safe_float(delta)


def build_feature_pipeline_spot_summary(
    *,
    spot_id: str,
    forecast_df: pd.DataFrame,
    feature_df: pd.DataFrame | None = None,
    validation: Any | None = None,
    stored_df: pd.DataFrame | None = None,
    status: str,
    error: str | None = None,
) -> dict[str, Any]:
    """Build the fixed observability contract for one feature-pipeline spot."""
    feature_frame = feature_df if feature_df is not None else pd.DataFrame()
    stored_frame = stored_df if stored_df is not None else pd.DataFrame()

    ingest_start, ingest_end, ingest_timezone = _time_window(forecast_df)
    ingest_units = _hourly_units(forecast_df)
    wind_speed_10m_unit = ingest_units.get("wind_speed_10m")
    wind_gusts_10m_unit = ingest_units.get("wind_gusts_10m")
    source_unit_contract_confirmed = (
        "wind_speed_10m" not in forecast_df.columns or wind_speed_10m_unit == "km/h"
    ) and ("wind_gusts_10m" not in forecast_df.columns or wind_gusts_10m_unit == "km/h")
    new_columns = sorted(set(feature_frame.columns) - set(forecast_df.columns))

    missing_columns = list(getattr(validation, "missing_columns", []) or [])
    null_fractions = dict(getattr(validation, "null_fractions", {}) or {})
    range_violations = getattr(validation, "range_violations", None)

    missing_after_roundtrip = sorted(
        set(feature_frame.columns) - set(stored_frame.columns)
    )
    extra_after_roundtrip = sorted(
        set(stored_frame.columns) - set(feature_frame.columns)
    )
    event_timestamp_source = _event_timestamp_source(
        stored_frame if not stored_frame.empty else feature_frame
    )

    return {
        "spot_id": spot_id,
        "status": status,
        "error": error,
        "ingest": {
            "rows": int(len(forecast_df)),
            "column_count": int(len(forecast_df.columns)),
            "time_start": ingest_start,
            "time_end": ingest_end,
            "timezone": ingest_timezone,
            "wind_speed_10m_unit": wind_speed_10m_unit,
            "wind_gusts_10m_unit": wind_gusts_10m_unit,
            "source_unit_contract_confirmed": source_unit_contract_confirmed,
            "hourly_units": ingest_units,
        },
        "engineering": {
            "rows": int(len(feature_frame)),
            "raw_column_count": int(len(forecast_df.columns)),
            "column_count": int(len(feature_frame.columns)),
            "engineered_column_count": int(len(new_columns)),
            "new_columns": new_columns,
        },
        "validation": {
            "is_valid": bool(getattr(validation, "is_valid", False)),
            "missing_column_count": int(len(missing_columns)),
            "missing_columns": missing_columns,
            "max_null_fraction": _max_null_fraction(null_fractions),
            "range_violation_count": _range_violation_count(range_violations),
        },
        "storage": {
            "stored_rows": int(len(stored_frame)),
            "stored_column_count": int(len(stored_frame.columns)),
            "missing_after_roundtrip_count": int(len(missing_after_roundtrip)),
            "extra_after_roundtrip_count": int(len(extra_after_roundtrip)),
            "missing_after_roundtrip": missing_after_roundtrip,
            "extra_after_roundtrip": extra_after_roundtrip,
            "max_numeric_abs_delta": _max_numeric_abs_delta(
                feature_frame, stored_frame
            ),
            "time_basis_preserved": _time_basis_preserved(feature_frame, stored_frame),
        },
        "feast": {
            "projection_ready": event_timestamp_source is not None and bool(spot_id),
            "event_timestamp_source": event_timestamp_source,
            "entity_key_ready": bool(spot_id),
        },
    }


def build_feature_pipeline_run_summary(
    *,
    dataset: str,
    storage_backend: str,
    expected_spots: list[str],
    fetched_spots: list[str],
    stored_spots: list[str],
    spot_summaries: list[dict[str, Any]],
    run_status: str,
    error: str | None = None,
) -> dict[str, Any]:
    """Build the persisted run summary for one end-to-end feature pipeline run."""
    return {
        "contract_version": 1,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "run_status": run_status,
        "error": error,
        "dataset": dataset,
        "storage_backend": storage_backend,
        "expected_spots": expected_spots,
        "fetched_spots": fetched_spots,
        "stored_spots": stored_spots,
        "expected_spot_count": int(len(expected_spots)),
        "fetched_spot_count": int(len(fetched_spots)),
        "stored_spot_count": int(len(stored_spots)),
        "skipped_spot_count": int(
            sum(summary["status"] == "skipped" for summary in spot_summaries)
        ),
        "failed_spot_count": int(
            sum(summary["status"] == "failed" for summary in spot_summaries)
        ),
        "spots": spot_summaries,
    }


def write_feature_pipeline_run_summary(summary: dict[str, Any]) -> Path:
    """Persist the latest run summary to a stable JSON file."""
    summary_path = feature_pipeline_summary_path(summary["dataset"])
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary_path


def read_feature_pipeline_run_summary(dataset: str = "train") -> dict[str, Any]:
    """Load the latest persisted feature-pipeline run summary."""
    summary_path = feature_pipeline_summary_path(dataset)
    return json.loads(summary_path.read_text())


def read_all_feature_pipeline_run_summaries() -> list[dict[str, Any]]:
    """Load all persisted feature-pipeline run summaries."""
    return [json.loads(path.read_text()) for path in feature_pipeline_summary_paths()]


def feature_pipeline_stage_overview(summary: dict[str, Any]) -> pd.DataFrame:
    """Flatten a persisted run summary into a notebook-friendly overview table."""
    rows: list[dict[str, Any]] = []

    for spot_summary in summary.get("spots", []):
        rows.append(
            {
                "spot_id": spot_summary["spot_id"],
                "status": spot_summary["status"],
                "error": spot_summary["error"],
                "ingest_rows": spot_summary["ingest"]["rows"],
                "wind_speed_10m_unit": spot_summary["ingest"].get(
                    "wind_speed_10m_unit"
                ),
                "wind_gusts_10m_unit": spot_summary["ingest"].get(
                    "wind_gusts_10m_unit"
                ),
                "source_unit_contract_confirmed": spot_summary["ingest"].get(
                    "source_unit_contract_confirmed"
                ),
                "engineered_rows": spot_summary["engineering"]["rows"],
                "engineered_new_columns": spot_summary["engineering"][
                    "engineered_column_count"
                ],
                "validation_passed": spot_summary["validation"]["is_valid"],
                "range_violation_count": spot_summary["validation"][
                    "range_violation_count"
                ],
                "stored_rows": spot_summary["storage"]["stored_rows"],
                "max_numeric_abs_delta": spot_summary["storage"][
                    "max_numeric_abs_delta"
                ],
                "time_basis_preserved": spot_summary["storage"]["time_basis_preserved"],
                "feast_projection_ready": spot_summary["feast"]["projection_ready"],
                "event_timestamp_source": spot_summary["feast"][
                    "event_timestamp_source"
                ],
            }
        )

    return pd.DataFrame(rows)


def _summary_metrics(summary: dict[str, Any]) -> dict[str, float]:
    metrics = {
        "feature_expected_spot_count": float(summary["expected_spot_count"]),
        "feature_fetched_spot_count": float(summary["fetched_spot_count"]),
        "feature_stored_spot_count": float(summary["stored_spot_count"]),
        "feature_skipped_spot_count": float(summary["skipped_spot_count"]),
        "feature_failed_spot_count": float(summary["failed_spot_count"]),
    }

    for spot_summary in summary.get("spots", []):
        prefix = f"feature_{spot_summary['spot_id']}"
        metrics[f"{prefix}_ingest_rows"] = float(spot_summary["ingest"]["rows"])
        metrics[f"{prefix}_source_unit_contract_confirmed"] = float(
            spot_summary["ingest"].get("source_unit_contract_confirmed", False)
        )
        metrics[f"{prefix}_engineered_rows"] = float(
            spot_summary["engineering"]["rows"]
        )
        metrics[f"{prefix}_validation_passed"] = float(
            spot_summary["validation"]["is_valid"]
        )
        metrics[f"{prefix}_range_violation_count"] = float(
            spot_summary["validation"]["range_violation_count"]
        )
        metrics[f"{prefix}_stored_rows"] = float(spot_summary["storage"]["stored_rows"])
        max_delta = spot_summary["storage"]["max_numeric_abs_delta"]
        if max_delta is not None:
            metrics[f"{prefix}_max_numeric_abs_delta"] = float(max_delta)
        metrics[f"{prefix}_feast_projection_ready"] = float(
            spot_summary["feast"]["projection_ready"]
        )

    return metrics


def emit_feature_pipeline_run_summary(summary: dict[str, Any]) -> Path:
    """Persist the latest summary and mirror stable metrics into MLflow if active."""
    summary_path = write_feature_pipeline_run_summary(summary)
    active_run = getattr(mlflow, "active_run", lambda: None)()
    if active_run is None:
        return summary_path

    mlflow.log_metrics(_summary_metrics(summary))
    mlflow.log_artifact(str(summary_path), artifact_path="monitoring/feature_pipeline")
    return summary_path


__all__ = [
    "FEATURE_PIPELINE_METRIC_CONTRACT",
    "build_feature_pipeline_run_summary",
    "build_feature_pipeline_spot_summary",
    "emit_feature_pipeline_run_summary",
    "feature_pipeline_summary_paths",
    "feature_pipeline_stage_overview",
    "feature_pipeline_summary_path",
    "read_all_feature_pipeline_run_summaries",
    "read_feature_pipeline_run_summary",
    "write_feature_pipeline_run_summary",
]
