"""Internal helpers shared across monitoring modules."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pandas as pd


def safe_float(value: Any) -> float | None:
    if value is None:
        return None
    numeric = float(value)
    if pd.isna(numeric):
        return None
    return numeric


def registered_model_version_metric_value(value: Any) -> float | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized.isdigit():
        return None
    return float(normalized)


def timestamp_seconds(value: Any, *, default_now: bool = False) -> float | None:
    if value in (None, ""):
        return datetime.now(UTC).timestamp() if default_now else None

    if isinstance(value, datetime):
        resolved = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return resolved.timestamp()

    text = str(value)
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        return float(datetime.fromisoformat(normalized).timestamp())
    except ValueError:
        return None
