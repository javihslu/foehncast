"""Regression tests for the main CI workflow contract."""

from __future__ import annotations

from tests.repo_helpers import (
    read_workflow_yaml as _workflow_yaml,
)


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
