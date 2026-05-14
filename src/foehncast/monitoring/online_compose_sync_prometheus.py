"""Prometheus export helpers for the hosted online-compose sync status file."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from prometheus_client import CollectorRegistry, Gauge, generate_latest

from foehncast._json import read_json_file_if_exists
from foehncast.monitoring._common import timestamp_seconds
from foehncast.paths import project_root


def _default_online_compose_sync_status_path() -> Path:
    return project_root() / ".state" / "online-compose-sync" / "last-success.json"


def read_online_compose_sync_status(
    status_path: Path | None = None,
) -> dict[str, Any] | None:
    """Load the latest hosted compose sync status if the file exists."""
    resolved_path = (
        _default_online_compose_sync_status_path()
        if status_path is None
        else status_path
    )
    return read_json_file_if_exists(resolved_path)


def build_online_compose_sync_prometheus_registry(
    status: dict[str, Any] | None = None,
) -> CollectorRegistry:
    """Render the hosted compose sync status file into a scrapeable registry."""
    resolved_status = read_online_compose_sync_status() if status is None else status
    registry = CollectorRegistry()

    status_file_present = Gauge(
        "foehncast_online_compose_sync_status_file_present",
        "Whether the hosted online-compose sync status file is available.",
        registry=registry,
    )
    status_file_present.set(float(resolved_status is not None))

    last_success_timestamp = Gauge(
        "foehncast_online_compose_sync_last_success_timestamp_seconds",
        "Unix timestamp of the latest successful hosted online-compose sync.",
        labelnames=("git_ref", "compose_deploy_mode"),
        registry=registry,
    )

    if resolved_status is None:
        return registry

    timestamp = timestamp_seconds(resolved_status.get("last_successful_sync_at"))
    if timestamp is None:
        return registry

    git_ref = str(resolved_status.get("git_ref") or "unknown")
    compose_deploy_mode = str(resolved_status.get("compose_deploy_mode") or "unknown")
    last_success_timestamp.labels(git_ref, compose_deploy_mode).set(timestamp)
    return registry


def render_online_compose_sync_prometheus_metrics(
    status: dict[str, Any] | None = None,
) -> bytes:
    """Return Prometheus exposition text for the hosted compose sync status."""
    registry = build_online_compose_sync_prometheus_registry(status=status)
    return generate_latest(registry)


__all__ = [
    "build_online_compose_sync_prometheus_registry",
    "read_online_compose_sync_status",
    "render_online_compose_sync_prometheus_metrics",
]
