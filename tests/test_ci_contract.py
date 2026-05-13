"""Regression tests for the main CI workflow contract."""

from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read_text(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text()


def _read_yaml(relative_path: str) -> dict:
    return yaml.safe_load(_read_text(relative_path))


def _workflow_yaml(relative_path: str) -> dict:
    workflow = _read_yaml(relative_path)
    if True in workflow and "on" not in workflow:
        workflow["on"] = workflow.pop(True)
    return workflow


def test_ci_workflow_runs_local_evaluator_smoke_after_compose_build() -> None:
    workflow = _workflow_yaml(".github/workflows/ci.yml")
    steps = workflow["jobs"]["compose"]["steps"]
    runs = [step["run"] for step in steps if "run" in step]
    uses = [step["uses"] for step in steps if "uses" in step]

    assert "astral-sh/setup-uv@v8.1.0" in uses
    assert (
        "docker compose -f docker-compose.yml build model-registry app airflow-webserver"
        in runs
    )
    assert "make smoke-local-evaluator" in runs
    assert runs.index(
        "docker compose -f docker-compose.yml build model-registry app airflow-webserver"
    ) < runs.index("make smoke-local-evaluator")
