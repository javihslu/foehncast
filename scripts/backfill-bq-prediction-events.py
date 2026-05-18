"""Backfill BigQuery prediction_events from local NDJSON via `bq load`.

Filters out rows that overlap the existing BigQuery time window, JSON-encodes
the requested_spot_ids array, and uses `bq load --source_format=NEWLINE_DELIMITED_JSON`.

Usage:
    PROJECT=mlops-hslu-h4izq DATASET=foehncast_monitoring TABLE=prediction_events \\
        python scripts/backfill-bq-prediction-events.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _iso_to_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _bq_minmax(table_fq: str) -> tuple[datetime | None, datetime | None]:
    res = subprocess.run(
        [
            "bq",
            "query",
            "--use_legacy_sql=false",
            "--format=json",
            f"SELECT MIN(prediction_timestamp) AS lo, MAX(prediction_timestamp) AS hi FROM `{table_fq}`",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    rows = json.loads(res.stdout)
    if not rows:
        return None, None
    lo_raw = rows[0].get("lo")
    hi_raw = rows[0].get("hi")
    lo = _iso_to_dt(lo_raw) if lo_raw else None
    hi = _iso_to_dt(hi_raw) if hi_raw else None
    return lo, hi


def main() -> int:
    project = os.environ.get("PROJECT", "mlops-hslu-h4izq")
    dataset = os.environ.get("DATASET", "foehncast_monitoring")
    table = os.environ.get("TABLE", "prediction_events")
    table_fq = f"{project}.{dataset}.{table}"

    jsonl = _PROJECT_ROOT / ".state" / "monitoring" / "prediction-events.jsonl"
    if not jsonl.exists():
        print(f"missing: {jsonl}", file=sys.stderr)
        return 1

    lo, hi = _bq_minmax(table_fq)
    print(f"existing BQ range: [{lo}, {hi}]  table={table_fq}")

    fd, out_path_str = tempfile.mkstemp(prefix="bq-backfill-", suffix=".ndjson")
    os.close(fd)
    out_path = Path(out_path_str)
    kept = 0
    skipped = 0
    with (
        jsonl.open("r", encoding="utf-8") as fh,
        out_path.open("w", encoding="utf-8") as out,
    ):
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            ts = _iso_to_dt(row["prediction_timestamp"])
            if lo is not None and hi is not None and lo <= ts <= hi:
                skipped += 1
                continue
            rsi = row.get("requested_spot_ids")
            if isinstance(rsi, list):
                row["requested_spot_ids"] = json.dumps(rsi)
            out.write(json.dumps(row) + "\n")
            kept += 1

    print(f"kept {kept} | skipped {skipped} | tmp={out_path}")
    if kept == 0:
        out_path.unlink(missing_ok=True)
        return 0

    cmd = [
        "bq",
        "load",
        "--source_format=NEWLINE_DELIMITED_JSON",
        "--noreplace",
        f"--project_id={project}",
        f"{dataset}.{table}",
        str(out_path),
    ]
    print("running:", " ".join(cmd))
    res = subprocess.run(cmd)
    out_path.unlink(missing_ok=True)
    return res.returncode


if __name__ == "__main__":
    raise SystemExit(main())
