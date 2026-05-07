"""Shared helpers for resolving project-local workload data paths."""

from __future__ import annotations

import os
from pathlib import Path


def _project_root_candidates() -> list[Path]:
    candidates: list[Path] = []

    configured_root = os.getenv("FOEHNCAST_PROJECT_ROOT", "").strip()
    if configured_root:
        candidates.append(Path(configured_root).expanduser())

    cwd = Path.cwd().resolve()
    candidates.extend([cwd, *cwd.parents])

    module_path = Path(__file__).resolve()
    candidates.extend(module_path.parents)
    return candidates


def _looks_like_project_root(path: Path) -> bool:
    return (path / "config.yaml").is_file() and any(
        marker.exists()
        for marker in (
            path / "pyproject.toml",
            path / "feature_repo" / "feature_store.yaml",
            path / "src" / "foehncast",
        )
    )


def project_root() -> Path:
    """Return the repository root for the foehncast project."""
    for candidate in _project_root_candidates():
        resolved = candidate.resolve()
        if _looks_like_project_root(resolved):
            return resolved

    return Path(__file__).resolve().parent.parent.parent


def workload_data_root() -> Path:
    """Return the canonical repo-local workload data root."""
    return project_root() / "data"


def feast_offline_path(dataset: str) -> Path:
    """Return the canonical local Feast export path for a dataset."""
    return workload_data_root() / "feast" / f"{dataset}.parquet"
