"""Optional Feast online feature access for application-side integrations."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from foehncast.inference_pipeline.predict import _resolve_spots

_DEFAULT_FEATURE_SERVICE = "foehncast_model_v1"
_DEFAULT_FEATURE_VIEW = "spot_forecast_features"


def _repo_path() -> Path:
    configured_path = os.getenv("FOEHNCAST_FEAST_REPO_PATH", "").strip()
    if configured_path:
        return Path(configured_path).expanduser()

    return Path(__file__).resolve().parents[3] / "feature_repo"


def _load_feature_store() -> Any:
    try:
        from feast import FeatureStore
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Feast is not installed in this environment. Run `uv sync --group feast` first."
        ) from exc

    repo_path = _repo_path()
    if not repo_path.exists():
        raise RuntimeError(f"Feast repo not found at {repo_path}")

    return FeatureStore(repo_path=str(repo_path))


def _feature_refs(feature_names: list[str]) -> list[str]:
    refs: list[str] = []

    for feature_name in feature_names:
        cleaned_name = feature_name.strip()
        if not cleaned_name:
            continue

        if ":" in cleaned_name:
            refs.append(cleaned_name)
        else:
            refs.append(f"{_DEFAULT_FEATURE_VIEW}:{cleaned_name}")

    if not refs:
        raise ValueError("At least one non-empty feature name must be provided")

    return refs


def _rows_from_columnar(
    columnar_features: dict[str, list[Any]],
) -> list[dict[str, Any]]:
    row_count = max((len(values) for values in columnar_features.values()), default=0)
    rows: list[dict[str, Any]] = []

    for index in range(row_count):
        rows.append({name: values[index] for name, values in columnar_features.items()})

    return rows


def get_online_spot_features(
    spot_ids: list[str] | None = None,
    feature_names: list[str] | None = None,
) -> dict[str, Any]:
    """Read the latest online features for configured spots via the local Feast repo."""
    requested_spots = _resolve_spots(spot_ids)
    entity_rows = [{"spot_id": spot["id"]} for spot in requested_spots]
    store = _load_feature_store()

    if feature_names:
        response = store.get_online_features(
            features=_feature_refs(feature_names),
            entity_rows=entity_rows,
        )
        feature_service = None
    else:
        response = store.get_online_features(
            features=store.get_feature_service(_DEFAULT_FEATURE_SERVICE),
            entity_rows=entity_rows,
        )
        feature_service = _DEFAULT_FEATURE_SERVICE

    columnar_features = response.to_dict()

    return {
        "feature_service": feature_service,
        "returned_features": [name for name in columnar_features if name != "spot_id"],
        "rows": _rows_from_columnar(columnar_features),
    }
