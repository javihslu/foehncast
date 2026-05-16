"""Tests for Prometheus export of hosted sync state."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from foehncast.monitoring import hosted_sync_prometheus
from tests.prometheus_assertions import metric_value


def test_render_hosted_sync_prometheus_metrics_reports_last_success() -> None:
    payload = hosted_sync_prometheus.render_hosted_sync_prometheus_metrics(
        {
            "state": "succeeded",
            "git_ref": "main",
            "last_successful_sync_at": "2026-05-11T18:50:00Z",
            "last_successful_commit": "abc123",
            "compose_deploy_mode": "pull",
        }
    ).decode("utf-8")

    assert "foehncast_online_compose_sync_status_file_present 1.0" in payload
    assert metric_value(
        payload,
        'foehncast_online_compose_sync_last_success_timestamp_seconds{compose_deploy_mode="pull",git_ref="main"}',
    ) == pytest.approx(1778525400.0)


def test_render_hosted_sync_prometheus_metrics_handles_missing_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        hosted_sync_prometheus,
        "_default_hosted_sync_status_path",
        lambda: tmp_path / "last-success.json",
    )

    payload = hosted_sync_prometheus.render_hosted_sync_prometheus_metrics(None).decode(
        "utf-8"
    )

    assert "foehncast_online_compose_sync_status_file_present 0.0" in payload
    assert "foehncast_online_compose_sync_last_success_timestamp_seconds" in payload


def test_read_hosted_sync_status_loads_json(tmp_path: Path) -> None:
    status_path = tmp_path / "last-success.json"
    status_path.write_text(
        json.dumps(
            {
                "state": "succeeded",
                "git_ref": "main",
                "last_successful_sync_at": "2026-05-11T18:50:00Z",
                "last_successful_commit": "abc123",
                "compose_deploy_mode": "build",
            }
        )
    )

    assert hosted_sync_prometheus.read_hosted_sync_status(status_path) == {
        "state": "succeeded",
        "git_ref": "main",
        "last_successful_sync_at": "2026-05-11T18:50:00Z",
        "last_successful_commit": "abc123",
        "compose_deploy_mode": "build",
    }
