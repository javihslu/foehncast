"""GCP helper functions: auth, triggers, workflow listing, Cloud Logging."""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

import streamlit as st

_WORKFLOWS_PROJECT = os.getenv("GCP_PROJECT_ID", "")
_WORKFLOWS_REGION = os.getenv("GCP_LOCATION", "")
_WORKFLOWS_NAME = os.getenv("FOEHNCAST_WORKFLOW_NAME", "foehncast-pipeline-cascade")

PIPELINE_JOB_NAMES = {
    "feature": os.getenv("FOEHNCAST_FEATURE_JOB_NAME", "foehncast-feature-pipeline"),
    "training": os.getenv("FOEHNCAST_TRAINING_JOB_NAME", "foehncast-training-pipeline"),
    "inference": os.getenv(
        "FOEHNCAST_INFERENCE_JOB_NAME", "foehncast-inference-pipeline"
    ),
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


def trigger_cloud_run_job(job_name: str) -> str | None:
    """Execute a single Cloud Run Job."""
    if not triggers_available() or not job_name:
        return None
    token = gcp_access_token()
    if not token:
        return None
    try:
        api_url = (
            f"https://run.googleapis.com/v2/projects/{_WORKFLOWS_PROJECT}/"
            f"locations/{_WORKFLOWS_REGION}/jobs/{job_name}:run"
        )
        req = urllib.request.Request(
            api_url,
            data=b"{}",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read()).get("name")
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
