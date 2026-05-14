"""Tests for shell-facing Airflow API helpers."""

from __future__ import annotations

import pytest

import foehncast.airflow_api as airflow_api


def test_airflow_api_health_errors_lists_unhealthy_required_components() -> None:
    errors = airflow_api.airflow_api_health_errors(
        {
            "metadatabase": {"status": "healthy"},
            "scheduler": {"status": "healthy"},
            "dag_processor": {"status": "starting"},
            "triggerer": {"status": "unhealthy"},
        }
    )

    assert errors == ["dag_processor='starting'", "triggerer='unhealthy'"]


def test_airflow_api_health_errors_rejects_non_object_json_payload() -> None:
    with pytest.raises(
        ValueError,
        match="Airflow API payload must decode to a JSON object.",
    ):
        airflow_api.airflow_api_health_errors('["not-an-object"]')


def test_airflow_dag_run_status_filters_by_run_type() -> None:
    result = airflow_api.airflow_dag_run_status(
        {
            "dag_runs": [
                {"dag_run_id": "manual__1", "run_type": "manual", "state": "queued"},
                {
                    "dag_run_id": "asset__1",
                    "run_type": "asset_triggered",
                    "state": "success",
                },
            ]
        },
        expected_state="success",
        expected_run_type="asset_triggered",
    )

    assert result["status"] == "success"
    assert result["dag_run_id"] == "asset__1"


def test_airflow_dag_run_status_reports_terminal_failure() -> None:
    result = airflow_api.airflow_dag_run_status(
        {
            "dag_runs": [
                {
                    "dag_run_id": "runtime_release__1",
                    "state": "failed",
                    "run_type": "manual",
                }
            ]
        },
        expected_state="success",
        expected_run_id="runtime_release__1",
    )

    assert result["status"] == "failed"
    assert result["state"] == "failed"
    assert result["run"]["dag_run_id"] == "runtime_release__1"
