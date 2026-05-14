"""Small helpers for reading environment bindings consistently."""

from __future__ import annotations

import os


def env_value(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value is None:
            continue
        stripped = value.strip()
        if stripped:
            return stripped
    return None
