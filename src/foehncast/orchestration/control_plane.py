"""Pipeline control-plane interface over Airflow and Cloud Workflows.

An `Orchestrator` protocol with an Airflow adapter (local, per-pipeline DAGs) and
a Cloud Workflows adapter (cloud, one cascade); `build_orchestrator` selects one
from the environment. No UI or serve dependency.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

import httpx

from foehncast.airflow_api import AirflowDagRun, list_dag_runs, trigger_dag
from foehncast.env import env_value


class OrchestratorError(RuntimeError):
    """Raised when an orchestrator cannot trigger a run or read run history."""


@dataclass(frozen=True)
class PipelineRun:
    """A single pipeline run, trimmed to what the control plane exposes."""

    run_id: str
    pipeline: str
    state: str
    started_at: str


@runtime_checkable
class Orchestrator(Protocol):
    """Trigger pipelines and list recent runs behind one interface."""

    def trigger(self, pipeline: str) -> PipelineRun: ...
    def list_runs(self, limit: int = 5) -> list[PipelineRun]: ...
    def capabilities(self) -> list[str]: ...


# Airflow adapter: one DAG per pipeline (dag ids from dags/*_dag.py).
_AIRFLOW_DAGS: dict[str, str] = {
    "feature": "feature_pipeline",
    "training": "training_pipeline",
    "inference": "inference_pipeline",
}


def _airflow_run(pipeline: str, run: AirflowDagRun) -> PipelineRun:
    return PipelineRun(
        run_id=run.dag_run_id,
        pipeline=pipeline,
        state=run.state,
        started_at=run.run_after or run.logical_date,
    )


class AirflowOrchestrator:
    """Wrap the airflow_api client; each pipeline maps to one DAG."""

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = base_url

    def capabilities(self) -> list[str]:
        return list(_AIRFLOW_DAGS)

    def trigger(self, pipeline: str) -> PipelineRun:
        dag_id = _AIRFLOW_DAGS.get(pipeline)
        if dag_id is None:
            raise OrchestratorError(f"unsupported pipeline: {pipeline!r}")
        result = trigger_dag(dag_id, base_url=self._base_url)
        if not result.ok:
            raise OrchestratorError(result.error or "airflow trigger failed")
        return PipelineRun(
            run_id=result.dag_run_id, pipeline=pipeline, state="queued", started_at=""
        )

    def list_runs(self, limit: int = 5) -> list[PipelineRun]:
        runs: list[PipelineRun] = []
        for pipeline, dag_id in _AIRFLOW_DAGS.items():
            result = list_dag_runs(dag_id, limit=limit, base_url=self._base_url)
            if result.error:
                raise OrchestratorError(result.error)
            runs.extend(_airflow_run(pipeline, run) for run in result.runs)
        runs.sort(key=lambda run: run.started_at, reverse=True)
        return runs[:limit]


# Workflows adapter: raw REST plus metadata-server token (no Google client libs).
_WORKFLOWS_API = "https://workflowexecutions.googleapis.com/v1"
_METADATA_TOKEN_URL = (
    "http://metadata.google.internal/computeMetadata/v1/"
    "instance/service-accounts/default/token"
)
_WORKFLOWS_TIMEOUT = 15.0
_DEFAULT_WORKFLOW = "foehncast-pipeline-cascade"


def _workflow_run(execution: Mapping[str, Any]) -> PipelineRun:
    return PipelineRun(
        run_id=str(execution.get("name") or ""),
        pipeline="cascade",
        state=str(execution.get("state") or "").lower(),
        started_at=str(execution.get("startTime") or execution.get("createTime") or ""),
    )


class WorkflowsOrchestrator:
    """Port of the ui/_gcp Cloud Workflows trigger/list logic; one cascade."""

    def __init__(
        self, *, project: str, region: str, workflow_name: str | None = None
    ) -> None:
        self._project = project
        self._region = region
        self._workflow = (
            workflow_name or env_value("FOEHNCAST_WORKFLOW_NAME") or _DEFAULT_WORKFLOW
        )

    def _executions_url(self) -> str:
        return (
            f"{_WORKFLOWS_API}/projects/{self._project}/locations/{self._region}"
            f"/workflows/{self._workflow}/executions"
        )

    def _request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            response = httpx.request(
                method,
                url,
                headers=dict(headers),
                json=payload,
                timeout=_WORKFLOWS_TIMEOUT,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            raise OrchestratorError(f"workflows request failed: {exc}") from exc

    def _token(self) -> str:
        data = self._request(
            "GET", _METADATA_TOKEN_URL, headers={"Metadata-Flavor": "Google"}
        )
        token = str(data.get("access_token") or "")
        if not token:
            raise OrchestratorError("metadata server returned no access token")
        return token

    def capabilities(self) -> list[str]:
        return ["cascade"]

    def trigger(self, pipeline: str) -> PipelineRun:
        # Workflows runs the single cascade regardless of the requested pipeline.
        token = self._token()
        data = self._request(
            "POST",
            self._executions_url(),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            payload={"argument": "{}"},
        )
        return _workflow_run(data)

    def list_runs(self, limit: int = 5) -> list[PipelineRun]:
        token = self._token()
        url = f"{self._executions_url()}?pageSize={limit}&orderBy=createTime%20desc"
        data = self._request("GET", url, headers={"Authorization": f"Bearer {token}"})
        return [_workflow_run(item) for item in data.get("executions", [])]


def build_orchestrator() -> Orchestrator | None:
    """Return the configured orchestrator, or None. Airflow on
    FOEHNCAST_AIRFLOW_API_URL, else Workflows on GCP_PROJECT_ID + GCP_LOCATION.
    """
    if env_value("FOEHNCAST_AIRFLOW_API_URL"):
        return AirflowOrchestrator()
    project = env_value("GCP_PROJECT_ID")
    region = env_value("GCP_LOCATION")
    if project and region:
        return WorkflowsOrchestrator(project=project, region=region)
    return None
