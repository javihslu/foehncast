#!/usr/bin/env python3
"""Backfill historical weather data, curate features, and generate prediction events.

Fetches 1 year of archive data from Open-Meteo for all configured spots,
engineers features through the standard pipeline, writes curated parquet
files to both local DVC-tracked storage and the S3 feature store, generates
synthetic prediction events, and optionally trains + registers a new model
in MLflow.

Usage:
    # Full backfill: archive data + predictions + train + promote
    python scripts/backfill-history.py

    # Archive data only (no predictions, no training)
    python scripts/backfill-history.py --no-predictions --no-train

    # Custom date range
    python scripts/backfill-history.py --start 2025-01-01 --end 2026-05-10

    # Skip DVC push (e.g. when MinIO is down)
    python scripts/backfill-history.py --no-push
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

# Ensure the project root is on sys.path so foehncast imports work.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from foehncast.config import get_rider_config, get_spots  # noqa: E402
from foehncast.feature_pipeline.engineer import engineer_features  # noqa: E402
from foehncast.feature_pipeline.validate import run_validation  # noqa: E402
from foehncast.training_pipeline.label import compute_quality_index  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Open-Meteo Archive API has a ~5-day lag; stop before that.
_ARCHIVE_LAG_DAYS = 7
_PREDICTION_EVENT_INTERVAL_HOURS = 6  # Simulate predictions every 6 h.
_API_PAUSE_SECONDS = 1.5  # Be polite to the free API.

# Archive API only provides surface-level data. Upper-level wind and
# convective indices must be approximated.
_WIND_PROFILE_EXPONENT = 0.143  # Power-law exponent for neutral stability.

# Params reliably available from the Open-Meteo archive API.
_ARCHIVE_HOURLY_PARAMS = (
    "wind_speed_10m,wind_gusts_10m,wind_direction_10m,"
    "temperature_2m,precipitation,relative_humidity_2m,"
    "cloud_cover,pressure_msl"
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--start",
        default=(datetime.now(tz=UTC) - timedelta(days=365)).strftime("%Y-%m-%d"),
        help="Start date (YYYY-MM-DD). Default: 1 year ago.",
    )
    parser.add_argument(
        "--end",
        default=(datetime.now(tz=UTC) - timedelta(days=_ARCHIVE_LAG_DAYS)).strftime(
            "%Y-%m-%d"
        ),
        help="End date (YYYY-MM-DD). Default: 7 days ago.",
    )
    parser.add_argument(
        "--dataset",
        default="train",
        help="Dataset name for output directory (default: train).",
    )
    parser.add_argument(
        "--no-predictions",
        action="store_true",
        help="Skip synthetic prediction event generation.",
    )
    parser.add_argument(
        "--model-version",
        default="2",
        help="Model version to stamp on synthetic prediction events.",
    )
    parser.add_argument(
        "--no-train",
        action="store_true",
        help="Skip MLflow training pipeline (train, register, promote).",
    )
    parser.add_argument(
        "--no-push",
        action="store_true",
        help="Skip DVC push after writing data.",
    )
    return parser.parse_args()


def _fetch_archive_raw(
    lat: float, lon: float, start_date: str, end_date: str
) -> pd.DataFrame:
    """Fetch archive data using only reliably available params."""
    import requests

    from foehncast.config import get_api_config
    from foehncast.http_client import ca_bundle

    cfg = get_api_config()["open_meteo"]
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": _ARCHIVE_HOURLY_PARAMS,
        "start_date": start_date,
        "end_date": end_date,
        "timezone": "UTC",  # Avoid DST ambiguity; convert to local TZ after.
        "wind_speed_unit": cfg.get("wind_speed_unit", "kmh"),
    }
    resp = requests.get(
        cfg["archive_url"], params=params, timeout=30, verify=ca_bundle()
    )
    resp.raise_for_status()
    data = resp.json()

    hourly = data.get("hourly", {})
    if not hourly:
        return pd.DataFrame()

    df = pd.DataFrame(hourly)
    # Timestamps arrive in UTC (we requested timezone=UTC to avoid DST gaps).
    # Convert to the configured local timezone for consistency with forecast data.
    tz = cfg["timezone"]
    timestamps = pd.to_datetime(df["time"], utc=True)
    timestamps = timestamps.dt.tz_convert(tz)
    df["time"] = timestamps
    df = df.set_index("time")
    return df


def _fill_missing_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Fill columns missing from the archive API with approximations.

    - wind_speed_80m / wind_speed_120m: power-law wind profile from 10m.
    - wind_direction_80m: same as 10m (direction is roughly constant).
    - cape / lifted_index: 0 (convective indices unavailable in archive).
    """
    import numpy as np

    out = df.copy()
    if "wind_speed_80m" not in out.columns:
        out["wind_speed_80m"] = (
            out["wind_speed_10m"] * (80.0 / 10.0) ** _WIND_PROFILE_EXPONENT
        )
    if "wind_speed_120m" not in out.columns:
        out["wind_speed_120m"] = (
            out["wind_speed_10m"] * (120.0 / 10.0) ** _WIND_PROFILE_EXPONENT
        )
    if "wind_direction_80m" not in out.columns:
        out["wind_direction_80m"] = out["wind_direction_10m"]
    if "cape" not in out.columns:
        out["cape"] = np.float64(0.0)
    if "lifted_index" not in out.columns:
        out["lifted_index"] = np.float64(0.0)
    return out


def _fetch_spot_archive(
    spot: dict, start_date: str, end_date: str
) -> pd.DataFrame | None:
    """Fetch and engineer features for a single spot."""
    spot_id = spot["id"]
    logger.info("Fetching %s (%s to %s)...", spot_id, start_date, end_date)

    try:
        raw_df = _fetch_archive_raw(spot["lat"], spot["lon"], start_date, end_date)
    except Exception:
        logger.exception("Failed to fetch %s", spot_id)
        return None

    if raw_df.empty:
        logger.warning("%s: empty response, skipping", spot_id)
        return None

    # Fill columns unavailable in the archive API.
    raw_df = _fill_missing_columns(raw_df)

    feature_df = engineer_features(
        raw_df,
        shore_orientation_deg=spot.get("shore_orientation_deg", 0),
    )

    validation = run_validation(feature_df, spot_id)
    if not validation.is_valid:
        logger.warning(
            "%s: validation failed (schema=%s, completeness=%s, range=%s)",
            spot_id,
            validation.schema_valid,
            validation.completeness_valid,
            validation.range_valid,
        )
        # Still write — archive data may have minor gaps.
        logger.info("%s: writing despite validation warnings", spot_id)

    logger.info("%s: %d rows engineered", spot_id, len(feature_df))
    return feature_df


def _generate_prediction_events(
    spot: dict,
    feature_df: pd.DataFrame,
    rider_config: dict,
    model_version: str,
) -> list[dict]:
    """Generate synthetic prediction events by applying the labeling function.

    Simulates predictions at regular intervals as if the model had been
    running. Since the model's label function is deterministic over the
    same features, the synthetic quality_index is what the model would
    have predicted.
    """
    spot_id = spot["id"]
    spot_name = spot["name"]

    quality = compute_quality_index(feature_df, rider_config)

    # Sample at the configured interval.
    interval = timedelta(hours=_PREDICTION_EVENT_INTERVAL_HOURS)
    timestamps = pd.date_range(
        start=feature_df.index.min(),
        end=feature_df.index.max(),
        freq=interval,
    )

    events = []
    for ts in timestamps:
        # Find the nearest row in the feature data.
        idx = feature_df.index.get_indexer([ts], method="nearest")[0]
        if idx < 0 or idx >= len(feature_df):
            continue

        forecast_time = feature_df.index[idx]
        qi = int(quality.iloc[idx])

        events.append(
            {
                "prediction_timestamp": ts.isoformat(),
                "forecast_time": forecast_time.isoformat(),
                "quality_index": qi,
                "endpoint": "backfill",
                "model_version": model_version,
                "spot_id": spot_id,
                "spot_name": spot_name,
                "requested_spot_ids": [spot_id],
            }
        )

    return events


def _write_prediction_events(events: list[dict], event_path: Path) -> None:
    """Append synthetic prediction events to the durable JSONL log."""
    event_path.parent.mkdir(parents=True, exist_ok=True)

    # Read existing events to avoid duplicates.
    existing_keys: set[tuple[str, str]] = set()
    if event_path.exists():
        with event_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    existing_keys.add(
                        (row.get("spot_id", ""), row.get("forecast_time", ""))
                    )
                except json.JSONDecodeError:
                    continue

    new_events = [
        e for e in events if (e["spot_id"], e["forecast_time"]) not in existing_keys
    ]

    if not new_events:
        logger.info("No new prediction events to write (all duplicates)")
        return

    with event_path.open("a", encoding="utf-8") as fh:
        for event in new_events:
            fh.write(json.dumps(event, sort_keys=True) + "\n")

    logger.info(
        "Wrote %d synthetic prediction events to %s", len(new_events), event_path
    )


def _write_to_feature_store(spots: list[dict], output_dir: Path) -> None:
    """Write backfilled parquets to the S3 feature store."""
    try:
        from foehncast.feature_pipeline.store import write_features  # noqa: E402
    except ImportError:
        logger.warning("Feature store not available — skipping S3 write")
        return

    for spot in spots:
        path = output_dir / f"{spot['id']}.parquet"
        if not path.exists():
            continue
        df = pd.read_parquet(path)
        write_features(df, spot_id=spot["id"], dataset="train")
        logger.info("%s: %d rows → S3 feature store", spot["id"], len(df))


def _run_mlflow_training() -> None:
    """Train, register, and promote model via MLflow."""
    from foehncast.training_pipeline.register import (
        register_model,  # noqa: E402
        promote_model,  # noqa: E402
    )
    from foehncast.training_pipeline.train import (
        run_training_pipeline,  # noqa: E402
    )

    logger.info("Running MLflow training pipeline...")
    run_id = run_training_pipeline(dataset="train")
    logger.info("MLflow run ID: %s", run_id)

    mv = register_model(run_id)
    logger.info("Registered model version: %s", mv.version)

    promote_model(model_name=None, version=mv.version, stage="Production")
    logger.info("Promoted model v%s to champion", mv.version)


def _dvc_push() -> None:
    """Push DVC-tracked data to the configured remote."""
    import subprocess

    logger.info("Pushing data to DVC remote...")
    result = subprocess.run(
        ["dvc", "push"],
        cwd=str(_PROJECT_ROOT),
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        logger.info("DVC push: %s", result.stdout.strip())
    else:
        logger.warning(
            "DVC push failed (may need credentials): %s", result.stderr.strip()
        )


def main() -> None:
    args = _parse_args()
    spots = get_spots()
    rider_config = get_rider_config()
    output_dir = _PROJECT_ROOT / "data" / args.dataset
    output_dir.mkdir(parents=True, exist_ok=True)

    event_path = _PROJECT_ROOT / ".state" / "monitoring" / "prediction-events.jsonl"
    working_log_path = _PROJECT_ROOT / ".state" / "monitoring" / "prediction-log.jsonl"

    logger.info(
        "Backfilling %d spots from %s to %s → %s",
        len(spots),
        args.start,
        args.end,
        output_dir,
    )

    all_events: list[dict] = []
    curated_count = 0

    for i, spot in enumerate(spots):
        if i > 0:
            time.sleep(_API_PAUSE_SECONDS)

        feature_df = _fetch_spot_archive(spot, args.start, args.end)
        if feature_df is None:
            continue

        # Write curated parquet.
        out_path = output_dir / f"{spot['id']}.parquet"
        feature_df.to_parquet(out_path)
        curated_count += 1
        logger.info("%s: %d rows → %s", spot["id"], len(feature_df), out_path.name)

        # Generate synthetic prediction events.
        if not args.no_predictions:
            events = _generate_prediction_events(
                spot, feature_df, rider_config, args.model_version
            )
            all_events.extend(events)
            logger.info("%s: %d synthetic prediction events", spot["id"], len(events))

    if curated_count == 0:
        logger.error("No spots produced valid data")
        sys.exit(1)

    # Write synthetic prediction events.
    if all_events and not args.no_predictions:
        _write_prediction_events(all_events, event_path)
        _write_prediction_events(all_events, working_log_path)

    # Write to S3 feature store.
    _write_to_feature_store(spots, output_dir)

    logger.info(
        "Done: %d/%d spots curated, %d prediction events",
        curated_count,
        len(spots),
        len(all_events),
    )

    # DVC push.
    if not args.no_push:
        _dvc_push()

    # MLflow training pipeline.
    if not args.no_train:
        _run_mlflow_training()

    logger.info("")
    logger.info("Backfill complete. Rebuild containers to pick up changes:")
    logger.info("  docker compose build app ui && docker compose up -d app ui")


if __name__ == "__main__":
    main()
