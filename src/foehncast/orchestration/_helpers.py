"""Shared orchestration utilities used across pipeline domains."""

from __future__ import annotations

from foehncast.env import env_value


def resolve_airflow_schedule(
    schedule: str | None, *, default: str | None = None
) -> str | None:
    """Normalize an Airflow schedule string, allowing explicit opt-out values."""
    candidate = default if schedule is None else schedule
    if candidate is None:
        return None

    normalized = candidate.strip()
    if not normalized:
        return None

    if normalized.lower() in {"none", "off", "false", "manual"}:
        return None

    return normalized


def resolve_auto_retraining_mode(
    mode: str | None, *, default: str | None = "always"
) -> str | None:
    """Normalize Airflow auto-retraining mode values."""
    candidate = default if mode is None else mode
    if candidate is None:
        return None

    normalized = candidate.strip().lower()
    if not normalized or normalized in {"none", "off", "false", "manual"}:
        return None

    if normalized in {"always", "new-data", "new_data", "on-success", "on_success"}:
        return "always"

    if normalized in {"drift", "drift-only", "drift_only"}:
        return "drift"

    raise ValueError(
        "Unsupported auto retraining mode. Use 'always', 'drift', or 'off'."
    )


def should_auto_retrain(
    feature_result: dict[str, object], mode: str | None = "always"
) -> bool:
    """Return whether the Airflow feature refresh should continue into retraining."""
    resolved_mode = resolve_auto_retraining_mode(mode, default="always")
    if resolved_mode is None:
        return False

    stored_spots = [
        str(spot_id).strip()
        for spot_id in feature_result.get("stored_spots", [])
        if str(spot_id).strip()
    ]
    if resolved_mode == "always":
        return bool(stored_spots)

    return bool(feature_result.get("dataset_drift_detected", False))


def scheduled_mlflow_tracking_uri() -> str | None:
    """Return the MLflow tracking URI from environment, or None if unset."""
    tracking_uri = env_value("MLFLOW_TRACKING_URI")
    return tracking_uri or None
