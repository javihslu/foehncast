"""Install a prediction snapshot so the console renders without the stack.

The UI reads .state/predictions/latest.json before it falls back to live
inference, so a valid snapshot is the only thing standing between a bare
checkout and a fully rendered rider console. That makes UI work and human
checks possible with no Airflow, MLflow, MinIO, or serving container.

    uv run python scripts/ui_fixture.py             # install (capture or synthetic)
    uv run python scripts/ui_fixture.py --capture   # record real predictions first

--capture needs the real stack up. It stores the payload in data/fixtures/ so
later runs can replay it offline. Without a stored capture, a synthetic
diurnal curve is generated instead.

Both paths mark model_version as a fixture. The console shows a banner on that
marker, because re-anchored or synthetic numbers must never read as a forecast.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

from foehncast.config import get_inference_config, get_spots
from foehncast.inference_pipeline.predict import (
    _SNAPSHOT_LOCATION,
    write_latest_predictions,
)

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "data/fixtures/predictions.json"
FIXTURE_PREFIX = "fixture"


def _anchor() -> pd.Timestamp:
    """Current hour in UTC: the snapshot has to cover now or the charts clip it."""
    return pd.Timestamp.now(tz="UTC").floor("h")


def _synthetic_payload() -> dict[str, Any]:
    """Deterministic diurnal quality curve per spot.

    Peaks mid-afternoon and bottoms out overnight, with a per-spot offset so the
    ranked order is not a tie and the heatmap has something to compare. No
    randomness: the same hour always yields the same board.
    """
    hours = int(get_inference_config()["max_horizon_hours"])
    start = _anchor()
    spots = get_spots()

    predictions = []
    for index, spot in enumerate(spots):
        # Spread spots across the ramp so the board shows firing and quiet side
        # by side rather than one flat colour.
        strength = 0.55 + 0.45 * (1.0 - index / max(len(spots) - 1, 1))
        rows = []
        for step in range(hours):
            time = start + pd.Timedelta(hours=step)
            # Local solar time drives the curve; 15:00 is the thermal peak.
            local_hour = (time.hour + spot["lon"] / 15.0) % 24.0
            diurnal = math.cos((local_hour - 15.0) / 24.0 * 2.0 * math.pi)
            quality = 2.6 * strength * (diurnal + 1.0) - 0.35 * (step / hours)
            rows.append(
                {
                    "time": time.isoformat(),
                    "quality_index": round(max(0.0, min(5.0, quality)), 3),
                }
            )
        predictions.append(
            {"spot_id": spot["id"], "spot_name": spot["name"], "forecast": rows}
        )

    return {"model_version": FIXTURE_PREFIX, "predictions": predictions}


def _replay(captured: dict[str, Any]) -> dict[str, Any]:
    """Shift a stored capture onto the current hour, keeping its shape."""
    times = [
        pd.Timestamp(row["time"])
        for spot in captured["predictions"]
        for row in spot["forecast"]
    ]
    if not times:
        return _synthetic_payload()

    shift = _anchor() - min(times).floor("h")
    predictions = [
        {
            **spot,
            "forecast": [
                {**row, "time": (pd.Timestamp(row["time"]) + shift).isoformat()}
                for row in spot["forecast"]
            ],
        }
        for spot in captured["predictions"]
    ]
    version = captured.get("model_version", "unknown")
    return {
        "model_version": f"{FIXTURE_PREFIX} (captured v{version})",
        "predictions": predictions,
    }


def capture() -> dict[str, Any]:
    """Run real inference once and store the payload for offline replay."""
    from foehncast.inference_pipeline.predict import predict_spots

    payload = predict_spots()
    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE_PATH.write_text(json.dumps(payload, indent=2, default=str), "utf-8")
    print(f"captured {len(payload['predictions'])} spots to {FIXTURE_PATH}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--capture",
        action="store_true",
        help="run real inference first (needs the stack) and store it",
    )
    args = parser.parse_args()

    if args.capture:
        payload = _replay(capture())
    elif FIXTURE_PATH.is_file():
        payload = _replay(json.loads(FIXTURE_PATH.read_text("utf-8")))
        print(f"replaying capture from {FIXTURE_PATH}")
    else:
        payload = _synthetic_payload()
        print("no stored capture; generated a synthetic curve")

    write_latest_predictions(payload)
    hours = len(payload["predictions"][0]["forecast"])
    print(
        f"installed {payload['model_version']} snapshot at {_SNAPSHOT_LOCATION} "
        f"({len(payload['predictions'])} spots x {hours} h from {_anchor()})"
    )


if __name__ == "__main__":
    main()
