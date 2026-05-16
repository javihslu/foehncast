"""Data provenance helpers for training lineage."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pandas as pd


def hash_parquet_files(data_dir: Path) -> str:
    """Return a hex digest of the sorted parquet files in a directory."""
    hasher = hashlib.sha256()
    for path in sorted(data_dir.glob("*.parquet")):
        hasher.update(path.name.encode())
        hasher.update(path.read_bytes())
    return hasher.hexdigest()


def hash_dataframe(df: pd.DataFrame) -> str:
    """Return a hex digest of a DataFrame's content."""
    return hashlib.sha256(pd.util.hash_pandas_object(df).values.tobytes()).hexdigest()


def get_git_commit() -> str:
    """Return the current git HEAD short hash, or 'unknown' outside a repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return "unknown"
