"""Helpers for exporting curated features into a Feast-friendly local dataset."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from foehncast.config import get_spots
from foehncast.feature_pipeline.store import read_features

_ROOT = Path(__file__).resolve().parent.parent.parent
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
    destination = (
        Path(output_path)
        if output_path
        else _ROOT / "data" / "feast" / f"{dataset}.parquet"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)

    offline_frame = build_offline_store_frame(dataset=dataset)
    offline_frame.to_parquet(destination, index=False)
    return destination


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
