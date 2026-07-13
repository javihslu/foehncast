"""GCP helper functions: auth, triggers, workflow listing, Cloud Logging."""

from __future__ import annotations

import json
import urllib.request
from typing import Any

import streamlit as st

from foehncast.env import env_value

_WORKFLOWS_PROJECT = env_value("GCP_PROJECT_ID") or ""
_WORKFLOWS_REGION = env_value("GCP_LOCATION") or ""
_WORKFLOWS_NAME = env_value("FOEHNCAST_WORKFLOW_NAME") or "foehncast-pipeline-cascade"

PIPELINE_JOB_NAMES = {
    "feature": env_value("FOEHNCAST_FEATURE_JOB_NAME") or "foehncast-feature-pipeline",
    "training": env_value("FOEHNCAST_TRAINING_JOB_NAME")
    or "foehncast-training-pipeline",
    "inference": env_value("FOEHNCAST_INFERENCE_JOB_NAME")
    or "foehncast-inference-pipeline",
}


def gcp_access_token() -> str | None:
    """Fetch a GCP access token from the metadata server (Cloud Run only)."""
    try:
        token_url = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"
        req = urllib.request.Request(token_url, headers={"Metadata-Flavor": "Google"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            return json.loads(resp.read()).get("access_token")
    except Exception:
        return None


def triggers_available() -> bool:
    return bool(_WORKFLOWS_PROJECT and _WORKFLOWS_REGION)


def in_cloud_runtime() -> bool:
    """True on Cloud Run (K_SERVICE is set) — use Cloud Workflows instead of Airflow."""
    return bool(env_value("K_SERVICE"))


def trigger_pipeline() -> str | None:
    """Trigger the Cloud Workflows pipeline cascade."""
    if not triggers_available():
        return None
    try:
        token = gcp_access_token()
        if not token:
            return None
        api_url = (
            f"https://workflowexecutions.googleapis.com/v1/"
            f"projects/{_WORKFLOWS_PROJECT}/locations/{_WORKFLOWS_REGION}/"
            f"workflows/{_WORKFLOWS_NAME}/executions"
        )
        body = json.dumps({"argument": "{}"}).encode()
        req = urllib.request.Request(
            api_url,
            data=body,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            return result.get("name")
    except Exception:
        return None


@st.cache_data(ttl=15, show_spinner=False)
def list_workflow_executions(limit: int = 5) -> list[dict[str, Any]]:
    """Return the most recent Cloud Workflows executions."""
    if not triggers_available():
        return []
    token = gcp_access_token()
    if not token:
        return []
    try:
        api_url = (
            f"https://workflowexecutions.googleapis.com/v1/"
            f"projects/{_WORKFLOWS_PROJECT}/locations/{_WORKFLOWS_REGION}/"
            f"workflows/{_WORKFLOWS_NAME}/executions"
            f"?pageSize={limit}&orderBy=createTime%20desc"
        )
        req = urllib.request.Request(
            api_url, headers={"Authorization": f"Bearer {token}"}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read()).get("executions", [])
    except Exception:
        return []


@st.cache_data(ttl=10, show_spinner=False)
def list_job_logs(job_name: str, limit: int = 8) -> list[dict[str, str]]:
    """Return the latest Cloud Logging entries for a Cloud Run Job."""
    if not _WORKFLOWS_PROJECT or not job_name:
        return []
    token = gcp_access_token()
    if not token:
        return []
    log_filter = (
        f'resource.type="cloud_run_job" '
        f'AND resource.labels.job_name="{job_name}" '
        f"AND severity>=DEFAULT"
    )
    body = json.dumps(
        {
            "resourceNames": [f"projects/{_WORKFLOWS_PROJECT}"],
            "filter": log_filter,
            "orderBy": "timestamp desc",
            "pageSize": limit,
        }
    ).encode()
    try:
        req = urllib.request.Request(
            "https://logging.googleapis.com/v2/entries:list",
            data=body,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.load(resp)
    except Exception:
        return []
    rows: list[dict[str, str]] = []
    for entry in data.get("entries", []):
        ts = entry.get("timestamp", "")
        severity = entry.get("severity", "INFO")
        message = (
            entry.get("textPayload")
            or entry.get("jsonPayload", {}).get("message")
            or ""
        )
        if not message:
            continue
        rows.append(
            {
                "timestamp": ts,
                "severity": severity,
                "message": str(message).strip(),
            }
        )
    return rows
