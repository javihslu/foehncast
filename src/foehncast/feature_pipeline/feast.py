"""Helpers for exporting curated features into a Feast-friendly local dataset."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

import pandas as pd

from foehncast.config import get_spots
from foehncast.env import env_value
from foehncast.feast_runtime import (
    feast_runtime_env,
    remove_non_writable_existing_file,
    render_runtime_config,
    require_existing_feast_repo_path,
)
from foehncast.feature_pipeline.store import read_features
from foehncast.paths import feast_offline_path

_EVENT_TIMESTAMP_COLUMN = "event_timestamp"


def _to_feast_frame(features_df: pd.DataFrame, spot_id: str) -> pd.DataFrame:
    frame = features_df.copy()

    if isinstance(frame.index, pd.DatetimeIndex):
        frame = frame.reset_index(names=_EVENT_TIMESTAMP_COLUMN)
    elif "time" in frame.columns:
        frame[_EVENT_TIMESTAMP_COLUMN] = pd.to_datetime(frame["time"], utc=True)
        frame = frame.drop(columns=["time"])
    else:
        raise KeyError(
            "Feast export requires feature rows with a DatetimeIndex or 'time' column"
        )

    frame[_EVENT_TIMESTAMP_COLUMN] = pd.to_datetime(
        frame[_EVENT_TIMESTAMP_COLUMN], utc=True
    )
    frame["spot_id"] = spot_id
    return frame


def build_offline_store_frame(dataset: str = "train") -> pd.DataFrame:
    """Concatenate stored feature rows into one frame for Feast offline retrieval."""
    frames: list[pd.DataFrame] = []

    for spot in get_spots():
        spot_id = spot["id"]
        try:
            features_df = read_features(spot_id=spot_id, dataset=dataset)
        except FileNotFoundError:
            continue

        if features_df.empty:
            continue

        frames.append(_to_feast_frame(features_df, spot_id=spot_id))

    if not frames:
        raise ValueError(
            f"No stored feature rows are available for dataset '{dataset}'"
        )

    combined = pd.concat(frames, ignore_index=True)
    return combined.sort_values([_EVENT_TIMESTAMP_COLUMN, "spot_id"]).reset_index(
        drop=True
    )


def build_entity_rows(dataset: str = "train") -> pd.DataFrame:
    """Return the entity dataframe Feast needs for historical retrieval."""
    offline_frame = build_offline_store_frame(dataset=dataset)
    return offline_frame[["spot_id", _EVENT_TIMESTAMP_COLUMN]].copy()


def export_offline_store(
    dataset: str = "train", output_path: str | Path | None = None
) -> Path:
    """Write the curated Feast offline dataset to a single local parquet file."""
    destination = Path(output_path) if output_path else feast_offline_path(dataset)
    destination.parent.mkdir(parents=True, exist_ok=True)

    remove_non_writable_existing_file(destination)

    offline_frame = build_offline_store_frame(dataset=dataset)
    offline_frame.to_parquet(destination, index=False)
    return destination


def _feast_python_executable() -> str:
    configured = env_value("FOEHNCAST_FEAST_PYTHON")
    return configured or sys.executable


def _feast_cli_command(args: list[str]) -> list[str]:
    configured_executable = Path(_feast_python_executable())
    configured_name = configured_executable.name

    if configured_name == "feast":
        return [str(configured_executable), *args]

    sibling_feast = configured_executable.with_name("feast")
    if sibling_feast.exists():
        return [str(sibling_feast), *args]

    feast_on_path = shutil.which("feast")
    if feast_on_path:
        return [feast_on_path, *args]

    return [str(configured_executable), "-m", "feast", *args]


def _run_feast_cli(
    args: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
) -> None:
    subprocess.run(
        _feast_cli_command(args),
        check=True,
        cwd=cwd,
        env=env,
        stdout=subprocess.DEVNULL,
    )


_MATERIALIZE_FALLBACK_LOOKBACK = timedelta(days=365)


def _materialize_start_timestamp(destination: Path | None) -> str:
    """Earliest timestamp to materialize from, so cold start covers the whole dataset.

    Reads the minimum event_timestamp from the freshly exported local parquet.
    BigQuery-sourced runs have no local parquet to inspect cheaply, so they
    fall back to a generous one-year lookback instead of querying BigQuery.
    """
    if destination is not None:
        offline_frame = pd.read_parquet(destination, columns=[_EVENT_TIMESTAMP_COLUMN])
        return offline_frame[_EVENT_TIMESTAMP_COLUMN].min().isoformat()

    return (datetime.now(tz=UTC) - _MATERIALIZE_FALLBACK_LOOKBACK).isoformat()


def prepare_feature_store(
    dataset: str = "train",
    *,
    output_path: str | Path | None = None,
    materialize: bool = True,
    materialize_timestamp: str | None = None,
) -> dict[str, Any]:
    """Sync the Feast repo: apply definitions and materialize the online store.

    A local parquet is exported only for the file-based offline store; BigQuery-source
    runs (the cloud pipeline) read the offline store straight from BigQuery.
    """
    repo_path = require_existing_feast_repo_path()
    source_mode = (env_value("FOEHNCAST_FEAST_SOURCE") or "local").strip().lower()
    destination = (
        None
        if source_mode == "bigquery"
        else export_offline_store(dataset=dataset, output_path=output_path)
    )
    config_path = render_runtime_config()
    env = feast_runtime_env(config_path)

    _run_feast_cli(["apply"], cwd=repo_path, env=env)

    resolved_materialize_timestamp = None
    if materialize:
        resolved_materialize_timestamp = (
            materialize_timestamp
            or datetime.now(tz=UTC).replace(microsecond=0).isoformat()
        )
        # Full range, not `-incremental` (see _materialize_start_timestamp):
        # the dataset is small, so this is cheap and idempotent to repeat.
        _run_feast_cli(
            [
                "materialize",
                _materialize_start_timestamp(destination),
                resolved_materialize_timestamp,
            ],
            cwd=repo_path,
            env=env,
        )

    return {
        "dataset": dataset,
        "output_path": str(destination) if destination else None,
        "config_path": str(config_path),
        "repo_path": str(repo_path),
        "materialized": materialize,
        "materialize_timestamp": resolved_materialize_timestamp,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    export_parser = subparsers.add_parser(
        "export", help="Export stored feature rows to a single Feast parquet file."
    )
    export_parser.add_argument("--dataset", default="train")
    export_parser.add_argument("--output", default=None)

    entities_parser = subparsers.add_parser(
        "entity-rows",
        help="Export the Feast entity dataframe used for historical retrieval.",
    )
    entities_parser.add_argument("--dataset", default="train")
    entities_parser.add_argument("--output", default=None)

    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    if args.command == "export":
        destination = export_offline_store(
            dataset=args.dataset, output_path=args.output
        )
        print(destination)
        return

    entity_rows = build_entity_rows(dataset=args.dataset)
    if args.output:
        destination = Path(args.output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        entity_rows.to_parquet(destination, index=False)
        print(destination)
        return

    print(entity_rows.to_csv(index=False))


if __name__ == "__main__":
    main()
