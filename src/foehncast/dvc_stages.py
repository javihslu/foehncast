"""Thin CLI entry points for DVC pipeline stages.

These wrappers call the same pipeline functions that Airflow uses, but write
outputs to the local filesystem so DVC can track them as stage artefacts.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def curate(dataset: str) -> None:
    """Run the feature pipeline for all configured spots and export to local parquet."""
    from foehncast.config import get_spots
    from foehncast.feature_pipeline.engineer import engineer_features
    from foehncast.feature_pipeline.ingest import fetch_all_spots
    from foehncast.feature_pipeline.validate import run_validation

    output_dir = _project_root() / "data" / dataset
    output_dir.mkdir(parents=True, exist_ok=True)

    spots = get_spots()
    spot_ids = [spot["id"] for spot in spots]
    spot_config = {spot["id"]: spot for spot in spots}

    print(f"Fetching forecasts for {len(spot_ids)} spots...")
    forecast_frames = fetch_all_spots(spot_ids)

    curated_count = 0
    for spot_id, forecast_df in forecast_frames.items():
        if forecast_df.empty:
            print(f"  {spot_id}: no forecast data, skipping")
            continue

        feature_df = engineer_features(
            forecast_df,
            shore_orientation_deg=spot_config[spot_id].get("shore_orientation_deg", 0),
        )

        validation = run_validation(feature_df)
        if not validation.is_valid:
            print(f"  {spot_id}: validation failed, skipping")
            continue

        out_path = output_dir / f"{spot_id}.parquet"
        feature_df.to_parquet(out_path)
        curated_count += 1
        print(f"  {spot_id}: {len(feature_df)} rows -> {out_path.name}")

    if curated_count == 0:
        print("No spots produced valid curated data", file=sys.stderr)
        sys.exit(1)

    print(f"Curated {curated_count}/{len(spot_ids)} spots to {output_dir}")


def train(dataset: str) -> None:
    """Train the model from local curated data and write metrics to reports/."""
    from foehncast.config import get_model_config, get_rider_config
    from foehncast.training_pipeline.evaluate import compute_metrics
    from foehncast.training_pipeline.label import label_dataset
    from foehncast.training_pipeline.train import train_model

    data_dir = _project_root() / "data" / dataset
    reports_dir = _project_root() / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    model_config = get_model_config()
    rider_config = get_rider_config()
    feature_columns = model_config["features"]
    target_column = model_config["target"]

    parquet_files = sorted(data_dir.glob("*.parquet"))
    if not parquet_files:
        print(f"No parquet files found in {data_dir}", file=sys.stderr)
        sys.exit(1)

    frames = []
    for path in parquet_files:
        df = pd.read_parquet(path)
        if not df.empty:
            frames.append(label_dataset(df, rider_config))

    if not frames:
        print("No labeled training data", file=sys.stderr)
        sys.exit(1)

    training_df = pd.concat(frames, ignore_index=True)
    missing = sorted(set([*feature_columns, target_column]) - set(training_df.columns))
    if missing:
        print(f"Missing columns: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    features = training_df[feature_columns].copy()
    target = training_df[target_column].copy()

    from sklearn.model_selection import train_test_split

    features_train, features_test, target_train, target_test = train_test_split(
        features,
        target,
        test_size=model_config["test_size"],
        random_state=model_config["random_state"],
    )

    print(f"Training on {len(features_train)} rows, testing on {len(features_test)}")
    model = train_model(features_train, target_train, model_config)
    predictions = model.predict(features_test)
    metrics = compute_metrics(target_test, predictions)
    metrics["training_row_count"] = len(features)
    metrics["training_feature_count"] = len(feature_columns)
    metrics["train_row_count"] = len(features_train)
    metrics["test_row_count"] = len(features_test)

    metrics_path = reports_dir / "train_metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2) + "\n")
    print(f"Metrics written to {metrics_path}")

    # Feature importance plot
    if hasattr(model, "feature_importances_"):
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        importance_df = pd.DataFrame(
            {"feature": feature_columns, "importance": model.feature_importances_}
        ).sort_values("importance", ascending=True)

        fig, ax = plt.subplots(figsize=(8, 4.5))
        ax.barh(importance_df["feature"], importance_df["importance"])
        ax.set_xlabel("Importance")
        ax.set_ylabel("Feature")
        ax.set_title("Feature importance")
        fig.tight_layout()
        plot_path = reports_dir / "feature_importance.png"
        fig.savefig(plot_path)
        plt.close(fig)
        print(f"Feature importance plot written to {plot_path}")

    for key in sorted(metrics):
        print(f"  {key}: {metrics[key]}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m foehncast.dvc_stages",
        description="DVC pipeline stage entry points",
    )
    subparsers = parser.add_subparsers(dest="stage", required=True)

    curate_parser = subparsers.add_parser("curate", help="Run feature curation")
    curate_parser.add_argument("--dataset", default="train")

    train_parser = subparsers.add_parser("train", help="Run model training")
    train_parser.add_argument("--dataset", default="train")

    args = parser.parse_args()

    if args.stage == "curate":
        curate(args.dataset)
    elif args.stage == "train":
        train(args.dataset)


if __name__ == "__main__":
    main()
