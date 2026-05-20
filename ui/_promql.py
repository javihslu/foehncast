"""PromQL query helpers for the Streamlit UI."""

from __future__ import annotations

import json
import os
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.parse import quote as urlquote

import streamlit as st

from _gcp import gcp_access_token

_PROMETHEUS_BASE_URL = os.getenv(
    "FOEHNCAST_PROMETHEUS_URL", "http://127.0.0.1:9090"
).rstrip("/")


@st.cache_data(ttl=30, show_spinner=False)
def prom_query(expr: str) -> float | None:
    """Run an instant PromQL query and return the scalar value, or *None*."""
    url = f"{_PROMETHEUS_BASE_URL}/api/v1/query?query={urlquote(expr)}"
    headers: dict[str, str] = {}
    if "monitoring.googleapis.com" in _PROMETHEUS_BASE_URL:
        token = gcp_access_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310
            data = json.load(resp)
        results = data.get("data", {}).get("result", [])
        if results:
            return float(results[0]["value"][1])
    except Exception:
        pass
    return None


def prom_query_batch(exprs: list[str]) -> list[float | None]:
    """Fan out multiple instant PromQL queries in parallel."""
    with ThreadPoolExecutor(max_workers=min(len(exprs), 8)) as pool:
        return list(pool.map(prom_query, exprs))


@st.cache_data(ttl=15, show_spinner=False)
def prom_query_vector(expr: str) -> list[dict[str, Any]]:
    """Run an instant PromQL query and return the full vector result."""
    url = f"{_PROMETHEUS_BASE_URL}/api/v1/query?query={urlquote(expr)}"
    headers: dict[str, str] = {}
    if "monitoring.googleapis.com" in _PROMETHEUS_BASE_URL:
        token = gcp_access_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
    out: list[dict[str, Any]] = []
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310
            data = json.load(resp)
        for entry in data.get("data", {}).get("result", []):
            labels = {
                k: v for k, v in entry.get("metric", {}).items() if k != "__name__"
            }
            try:
                value = float(entry["value"][1])
            except (KeyError, ValueError, TypeError):
                continue
            out.append({"labels": labels, "value": value})
    except Exception:
        pass
    return out
