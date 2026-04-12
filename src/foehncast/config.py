"""Load and manage configuration from config.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_ROOT = Path(__file__).resolve().parent.parent.parent  # foehncast/
_CONFIG_PATH = _ROOT / "config.yaml"
_config: dict[str, Any] | None = None


def load_config(path: Path | None = None) -> dict[str, Any]:
    """Load config.yaml and cache it."""
    global _config
    if _config is None or path is not None:
        p = path or _CONFIG_PATH
        with open(p) as f:
            _config = yaml.safe_load(f)
    return _config


def get_spots() -> list[dict[str, Any]]:
    """Return the list of spot configurations."""
    return load_config()["spots"]


def get_api_config() -> dict[str, Any]:
    """Return the api section of the config."""
    return load_config()["api"]


def get_rider_config() -> dict[str, Any]:
    """Return the rider profile."""
    return load_config()["rider"]


def get_model_config() -> dict[str, Any]:
    """Return the model training settings."""
    return load_config()["model"]
