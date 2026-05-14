"""Private timestamp normalization helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def compact_utc_timestamp(value: Any | None = None) -> str:
    timestamp = _coerced_datetime(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    else:
        timestamp = timestamp.astimezone(UTC)
    return timestamp.strftime("%Y%m%dT%H%M%S%fZ")


def _coerced_datetime(value: Any | None) -> datetime:
    if isinstance(value, datetime):
        return value

    if value is not None:
        text = str(value).strip()
        if text:
            try:
                return datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError:
                pass

    return datetime.now(tz=UTC)