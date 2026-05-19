"""Streamlit rider console for FoehnCast spot recommendations."""

from __future__ import annotations

import json
import os
import time as _time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.parse import quote as urlquote

import streamlit as st

import math

import altair as alt
import pandas as pd

from foehncast.config import get_rider_config, get_spots
from foehncast.inference_pipeline.dashboard import (
    list_dashboard_spots,
    load_dashboard_data,
)
from foehncast.feature_pipeline.ingest import fetch_forecast

st.set_page_config(
    page_title="FoehnCast Rider Console",
    layout="wide",
    initial_sidebar_state="expanded",
)

_PROMETHEUS_BASE_URL = os.getenv(
    "FOEHNCAST_PROMETHEUS_URL", "http://127.0.0.1:9090"
).rstrip("/")

_WORKFLOWS_PROJECT = os.getenv("GCP_PROJECT_ID", "")
_WORKFLOWS_REGION = os.getenv("GCP_LOCATION", "")
_WORKFLOWS_NAME = os.getenv("FOEHNCAST_WORKFLOW_NAME", "foehncast-pipeline-cascade")


_PIPELINE_JOB_NAMES = {
    "feature": os.getenv("FOEHNCAST_FEATURE_JOB_NAME", "foehncast-feature-pipeline"),
    "training": os.getenv("FOEHNCAST_TRAINING_JOB_NAME", "foehncast-training-pipeline"),
    "inference": os.getenv(
        "FOEHNCAST_INFERENCE_JOB_NAME", "foehncast-inference-pipeline"
    ),
}


def _trigger_pipeline() -> str | None:
    """Trigger the Cloud Workflows pipeline cascade and return the execution name.

    Returns ``None`` when the required env vars are not set (local dev) or
    when the request fails.
    """
    if not _WORKFLOWS_PROJECT or not _WORKFLOWS_REGION:
        return None
    try:
        # On Cloud Run the default SA metadata token works for authenticated calls.
        token_url = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"
        token_req = urllib.request.Request(
            token_url, headers={"Metadata-Flavor": "Google"}
        )
        with urllib.request.urlopen(token_req, timeout=5) as resp:
            token = json.loads(resp.read())["access_token"]

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


def _trigger_cloud_run_job(job_name: str) -> str | None:
    """Execute a single Cloud Run Job and return the execution name on success."""
    if not _WORKFLOWS_PROJECT or not _WORKFLOWS_REGION or not job_name:
        return None
    token = _gcp_access_token()
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
def _list_workflow_executions(limit: int = 5) -> list[dict[str, Any]]:
    """Return the most recent Cloud Workflows executions (best effort)."""
    if not _WORKFLOWS_PROJECT or not _WORKFLOWS_REGION:
        return []
    token = _gcp_access_token()
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


@st.cache_data(show_spinner=False)
def _available_spots() -> list[dict[str, Any]]:
    return list_dashboard_spots()


@st.cache_data(ttl=900, show_spinner=False)
def _live_dashboard_data(selected_spot_ids: tuple[str, ...]) -> dict[str, Any]:
    return load_dashboard_data(list(selected_spot_ids) if selected_spot_ids else None)


@st.cache_data(ttl=900, show_spinner=False)
def _focus_spot_timeline(spot_id: str, *, past_days: int = 1) -> pd.DataFrame:
    """Return wind speed at three elevations for a single spot.

    The Open-Meteo forecast endpoint, called with ``past_days``, returns
    analysed/observed hours before now and the standard forecast horizon
    after. We surface the raw ``wind_speed_{10,80,120}m`` series so the
    rider can compare observed and predicted wind directly. The 12 kn
    rideability threshold (~22.2 km/h) is drawn on top by the chart.
    """
    spot = next((s for s in get_spots() if s["id"] == spot_id), None)
    if spot is None:
        return pd.DataFrame(columns=["time", "elevation", "wind_speed"])

    forecast_df = fetch_forecast(spot["lat"], spot["lon"], past_days=past_days)
    if forecast_df.empty:
        return pd.DataFrame(columns=["time", "elevation", "wind_speed"])

    wide = forecast_df.reset_index().rename(columns={"index": "time"})
    keep = [
        c
        for c in ("wind_speed_10m", "wind_speed_80m", "wind_speed_120m")
        if c in wide.columns
    ]
    if not keep:
        return pd.DataFrame(columns=["time", "elevation", "wind_speed"])
    long = wide[["time", *keep]].melt(
        id_vars="time", var_name="elevation", value_name="wind_speed"
    )
    long["elevation"] = long["elevation"].str.replace("wind_speed_", "")
    long["time"] = pd.to_datetime(long["time"])
    return long


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
          @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;600;700;800&family=Newsreader:opsz,wght@6..72,500;6..72,700&display=swap');

          :root {
            --bg: #c4d9d2;
            --panel: rgba(255, 255, 255, 0.82);
            --panel-strong: rgba(255, 255, 255, 0.94);
            --ink: #07252a;
            --muted: #3b5a5a;
            --accent: #0e8a86;
            --accent-soft: rgba(14, 138, 134, 0.16);
            --pine: #1f5e44;
            --pine-soft: rgba(31, 94, 68, 0.16);
            --warm: #ff7a26;
            --warm-soft: rgba(255, 122, 38, 0.20);
            --line: rgba(7, 37, 42, 0.18);
            --shadow: 0 20px 60px rgba(7, 37, 42, 0.14);
          }

          .stApp {
            background:
              radial-gradient(circle at 12% 8%, rgba(14, 138, 134, 0.28), transparent 38%),
              radial-gradient(circle at 88% 6%, rgba(31, 94, 68, 0.28), transparent 36%),
              radial-gradient(circle at 70% 90%, rgba(255, 122, 38, 0.14), transparent 40%),
              linear-gradient(180deg, #d4e6df 0%, var(--bg) 100%);
            color: var(--ink);
          }

          .block-container {
            padding-top: 0.6rem;
            padding-bottom: 2rem;
          }

          /* Hide Streamlit's default top chrome so our nav owns the top */
          header[data-testid="stHeader"],
          div[data-testid="stDecoration"],
          div[data-testid="stToolbar"] {
            display: none !important;
          }
          div[data-testid="stAppViewContainer"] > .main,
          div[data-testid="stAppViewContainer"] section.main {
            padding-top: 0 !important;
          }

          /* Top-nav style tab bar — matches olive-grey buttons */
          div[data-testid="stTabs"] > div[role="tablist"] {
            position: sticky;
            top: 0;
            z-index: 50;
            margin: -0.6rem -2rem 1.4rem -2rem;
            padding: 0.55rem 2rem 0.55rem;
            background: rgba(34, 41, 38, 0.92);
            backdrop-filter: blur(8px);
            -webkit-backdrop-filter: blur(8px);
            border-bottom: 1px solid rgba(7, 37, 42, 0.45);
            box-shadow: 0 4px 16px rgba(7, 37, 42, 0.18);
            gap: 0.5rem;
          }
          div[data-testid="stTabs"] > div[role="tablist"] button[role="tab"] {
            font-family: 'Manrope', sans-serif !important;
            font-weight: 700 !important;
            font-size: 0.95rem;
            color: #e4e2db !important;
            padding: 0.6rem 1rem;
            border-bottom: 2px solid transparent;
            background: transparent;
            border-radius: 10px 10px 0 0;
            transition: background 0.15s ease, color 0.15s ease;
          }
          div[data-testid="stTabs"] > div[role="tablist"] button[role="tab"]:hover {
            background: rgba(77, 84, 80, 0.55);
            color: #ffffff !important;
          }
          div[data-testid="stTabs"] > div[role="tablist"] button[role="tab"][aria-selected="true"] {
            color: var(--warm) !important;
            background: #4d5450;
            border-bottom-color: var(--warm);
          }
          div[data-testid="stTabs"] > div[role="tablist"] div[data-baseweb="tab-highlight"] {
            display: none;
          }

          button[role="tab"] {
            font-family: 'Manrope', sans-serif;
            font-weight: 700;
          }

          h1, h2, h3 {
            font-family: 'Newsreader', serif;
            color: var(--ink);
            letter-spacing: -0.02em;
          }

          p, li, div[data-testid="stMarkdownContainer"] {
            font-family: 'Manrope', sans-serif;
          }

          /* Transparent chart backgrounds (Altair / Vega / Plotly canvas) */
          div[data-testid="stVegaLiteChart"],
          div[data-testid="stPlotlyChart"],
          .vega-embed,
          .vega-embed canvas,
          .vega-embed svg {
            background: transparent !important;
          }

          /* Matt olive-grey buttons; selected (kind="primary") uses warm orange text */
          div[data-testid="stButton"] > button,
          div[data-testid="stFormSubmitButton"] > button {
            background: #4d5450 !important;
            background-image: none !important;
            color: #e4e2db !important;
            border: 1px solid rgba(7, 37, 42, 0.32) !important;
            border-radius: 12px !important;
            box-shadow: none !important;
            font-family: 'Manrope', sans-serif !important;
            font-weight: 700 !important;
            height: 44px !important;
            min-height: 44px !important;
            padding: 0 14px !important;
            width: 100% !important;
            white-space: nowrap !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
            transition: background 0.15s ease, color 0.15s ease;
          }
          div[data-testid="stButton"] > button:hover,
          div[data-testid="stFormSubmitButton"] > button:hover {
            background: #404641 !important;
            color: #ffffff !important;
            border-color: rgba(7, 37, 42, 0.40) !important;
          }
          div[data-testid="stButton"] > button[kind="primary"],
          div[data-testid="stButton"] > button[data-testid="baseButton-primary"] {
            background: #404641 !important;
            color: var(--warm) !important;
            border-color: rgba(255, 122, 38, 0.55) !important;
            border-bottom-left-radius: 0 !important;
            border-bottom-right-radius: 0 !important;
            border-bottom-color: rgba(255, 122, 38, 0.55) !important;
            margin-bottom: 0 !important;
          }
          div[data-testid="stButton"] > button[kind="primary"]:hover {
            background: #363b37 !important;
            color: var(--warm) !important;
          }

          /* Transposed ranked-recommendations grid — mirrors st.columns layout so
             spot columns line up under each switcher button. */
          .ranked-stack {
            display: grid;
            gap: 1rem;
            width: 100%;
            margin-top: -1px;
            font-family: 'Manrope', sans-serif;
          }
          .ranked-stack .col {
            display: flex;
            flex-direction: column;
          }
          .ranked-stack .col.lead {
            text-align: right;
            color: var(--muted);
            padding-top: 8px;
          }
          .ranked-stack .col.lead .cell {
            font-size: 0.72rem;
            font-weight: 700;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            padding: 6px 12px;
          }
          .ranked-stack .col.spot {
            text-align: center;
            color: var(--ink);
            padding: 8px 12px 12px;
            border: 1px solid transparent;
            border-top: none;
            border-bottom-left-radius: 12px;
            border-bottom-right-radius: 12px;
          }
          .ranked-stack .col.spot.active {
            background: #404641;
            color: var(--warm);
            font-weight: 700;
            border-color: rgba(255, 122, 38, 0.55);
          }
          .ranked-stack .col.spot .cell {
            font-size: 0.9rem;
            padding: 6px 0;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
          }

          /* Spot map panel */
          .spot-map-shell {
            border: 1px solid var(--line);
            border-radius: 28px;
            background: var(--panel);
            box-shadow: var(--shadow);
            padding: 18px 22px 22px;
            margin-top: 1rem;
          }
          .spot-map-shell p.eyebrow {
            margin-bottom: 8px;
          }

          section[data-testid="stSidebar"] {
            background: rgba(210, 226, 220, 0.88);
            border-right: 1px solid var(--line);
            color: var(--ink);
          }

          section[data-testid="stSidebar"] p,
          section[data-testid="stSidebar"] span,
          section[data-testid="stSidebar"] div[data-testid="stMarkdownContainer"],
          section[data-testid="stSidebar"] .stCaption,
          section[data-testid="stSidebar"] label {
            color: var(--ink) !important;
          }

          /* Sidebar buttons keep cream text on olive-grey, overriding the
             sidebar ink-color rule above. */
          section[data-testid="stSidebar"] div[data-testid="stButton"] > button,
          section[data-testid="stSidebar"] div[data-testid="stButton"] > button p,
          section[data-testid="stSidebar"] div[data-testid="stButton"] > button span,
          section[data-testid="stSidebar"] div[data-testid="stButton"] > button div {
            color: #e4e2db !important;
          }
          section[data-testid="stSidebar"] div[data-testid="stButton"] > button:hover,
          section[data-testid="stSidebar"] div[data-testid="stButton"] > button:hover p,
          section[data-testid="stSidebar"] div[data-testid="stButton"] > button:hover span,
          section[data-testid="stSidebar"] div[data-testid="stButton"] > button:hover div {
            color: #ffffff !important;
          }

          div[data-testid="stMetric"] {
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 20px;
            padding: 16px 18px;
            box-shadow: var(--shadow);
          }

          .hero-shell,
          .feature-card,
          .profile-card,
          .top-pick {
            border: 1px solid var(--line);
            border-radius: 28px;
            background: var(--panel);
            box-shadow: var(--shadow);
          }

          .hero-shell {
            padding: 28px 30px;
            margin-bottom: 1.2rem;
          }

          .eyebrow {
            margin: 0 0 8px;
            font-family: 'Manrope', sans-serif;
            font-size: 0.85rem;
            font-weight: 800;
            letter-spacing: 0.18em;
            text-transform: uppercase;
            color: var(--accent);
          }

          .hero-title {
            margin: 0;
            font-size: clamp(2.5rem, 5vw, 4.2rem);
            line-height: 0.95;
          }

          .hero-lede {
            margin: 12px 0 0;
            max-width: 68ch;
            color: var(--muted);
            font-size: 1.02rem;
            line-height: 1.6;
          }

          .top-pick {
            padding: 24px 26px;
            margin-bottom: 1rem;
            background:
              linear-gradient(135deg, rgba(14, 138, 134, 0.10), rgba(255, 122, 38, 0.12)),
              var(--panel-strong);
          }

          .top-pick h3,
          .profile-card h3 {
            margin: 0 0 10px;
            font-size: 1.6rem;
          }

          .spot-line {
            margin: 0;
            color: var(--muted);
            font-size: 0.98rem;
          }

          .stat-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
            gap: 12px;
            margin-top: 16px;
          }

          .stat-chip {
            border-radius: 18px;
            padding: 12px 14px;
            background: rgba(255, 255, 255, 0.82);
            border: 1px solid var(--line);
          }

          .stat-chip span {
            display: block;
            color: var(--muted);
            font-size: 0.78rem;
            font-weight: 700;
            letter-spacing: 0.04em;
            text-transform: uppercase;
          }

          .stat-chip strong {
            display: block;
            margin-top: 4px;
            font-family: 'Newsreader', serif;
            font-size: 1.35rem;
            color: var(--ink);
          }

          .profile-card {
            padding: 18px 18px 10px;
            margin-top: 1rem;
          }

          .profile-row {
            display: flex;
            justify-content: space-between;
            gap: 12px;
            padding: 10px 0;
            border-top: 1px solid rgba(23, 50, 77, 0.08);
            color: var(--muted);
            font-size: 0.94rem;
          }

          .profile-row:first-of-type {
            border-top: 0;
            padding-top: 0;
          }

          .profile-row strong {
            color: var(--ink);
            font-weight: 800;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _spot_label(spot_lookup: dict[str, dict[str, Any]], spot_id: str) -> str:
    spot = spot_lookup[spot_id]
    return f"{spot['name']} ({spot_id})"


def _profile_card(rider_profile: dict[str, Any]) -> str:
    quiver = ", ".join(str(size) for size in rider_profile.get("quiver_m2", []))
    return f"""
    <section class="profile-card">
      <p class="eyebrow">Configured Rider</p>
      <h3>{rider_profile["home_location"]}</h3>
      <div class="profile-row"><span>Weight</span><strong>{rider_profile["weight_kg"]} kg</strong></div>
      <div class="profile-row"><span>Home coordinates</span><strong>{rider_profile["home_lat"]}, {rider_profile["home_lon"]}</strong></div>
      <div class="profile-row"><span>Quiver</span><strong>{quiver} m²</strong></div>
    </section>
    """


def _top_pick_card(top_spot: dict[str, Any], model_version: str) -> str:
    return f"""
    <section class="top-pick">
      <p class="eyebrow">Top Recommendation</p>
      <h3>{top_spot["spot_name"]}</h3>
      <p class="spot-line">
        Signal: <strong>{top_spot["quality_label"]}</strong> · Best window {top_spot["peak_time_label"]} · Model v{model_version}
      </p>
      <div class="stat-grid">
        <div class="stat-chip"><span>Peak quality</span><strong>{top_spot["quality_index"]:.2f}</strong></div>
        <div class="stat-chip"><span>Rideable hours</span><strong>{top_spot["rideable_hours"]}</strong></div>
        <div class="stat-chip"><span>Drive time</span><strong>{top_spot["drive_minutes"]:.0f} min</strong></div>
        <div class="stat-chip"><span>Ride / drive</span><strong>{top_spot["ride_drive_ratio"]:.2f}</strong></div>
      </div>
    </section>
    """


def _gcp_access_token() -> str | None:
    """Fetch a GCP access token from the metadata server (Cloud Run only)."""
    try:
        token_url = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"
        req = urllib.request.Request(token_url, headers={"Metadata-Flavor": "Google"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            return json.loads(resp.read()).get("access_token")
    except Exception:
        return None


@st.cache_data(ttl=30, show_spinner=False)
def _prom_query(expr: str) -> float | None:
    """Run an instant PromQL query and return the scalar value, or *None*.

    Results are cached for 30 s to avoid redundant HTTP round-trips on
    every Streamlit widget interaction.

    When the Prometheus URL points to a GMP endpoint (contains
    ``monitoring.googleapis.com``), an OAuth2 bearer token is attached
    automatically using the Cloud Run metadata server.
    """
    url = f"{_PROMETHEUS_BASE_URL}/api/v1/query?query={urlquote(expr)}"
    headers: dict[str, str] = {}
    if "monitoring.googleapis.com" in _PROMETHEUS_BASE_URL:
        token = _gcp_access_token()
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


def _prom_query_batch(exprs: list[str]) -> list[float | None]:
    """Fan out multiple instant PromQL queries in parallel.

    Returns a list of scalar values (or None) in the same order as *exprs*.
    This eliminates sequential round-trip latency to Cloud Run — critical
    when the serve container is on a separate Cloud Run instance with
    ~100-200ms per request.
    """
    with ThreadPoolExecutor(max_workers=min(len(exprs), 8)) as pool:
        return list(pool.map(_prom_query, exprs))


@st.cache_data(ttl=15, show_spinner=False)
def _prom_query_vector(expr: str) -> list[dict[str, Any]]:
    """Run an instant PromQL query and return the full vector result.

    Each entry is ``{"labels": {...}, "value": float}``. Returns an empty
    list on any error or empty result. Cached briefly so the System tab
    fanning out across many stages does not hammer the serve container.
    """
    url = f"{_PROMETHEUS_BASE_URL}/api/v1/query?query={urlquote(expr)}"
    headers: dict[str, str] = {}
    if "monitoring.googleapis.com" in _PROMETHEUS_BASE_URL:
        token = _gcp_access_token()
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


@st.cache_data(ttl=10, show_spinner=False)
def _list_job_logs(job_name: str, limit: int = 8) -> list[dict[str, str]]:
    """Return the latest Cloud Logging entries for a Cloud Run Job.

    Best effort: requires ``roles/logging.viewer`` on the UI service
    account. Returns an empty list when the request fails or the env is
    not configured.
    """
    if not _WORKFLOWS_PROJECT or not job_name:
        return []
    token = _gcp_access_token()
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


_PREDICTION_CYCLE_SECONDS = 6 * 3600  # Airflow schedule: 0 */6 * * *


def _fmt_delta(seconds: float) -> str:
    """Format a duration in seconds to a short human-readable string."""
    s = abs(int(seconds))
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m"
    h, m = divmod(s, 3600)
    return f"{h}h {m // 60}m"


def _freshness_circle_html(
    label: str,
    elapsed: float,
    *,
    scheduled: bool,
) -> str:
    """Build HTML for a single circular freshness indicator.

    When *scheduled* is True the ring counts down against the 6 h pipeline
    cycle.  When False the ring is a static age-only badge (no countdown).
    """
    if scheduled:
        remaining = max(0.0, _PREDICTION_CYCLE_SECONDS - elapsed)
        pct = min(1.0, elapsed / _PREDICTION_CYCLE_SECONDS)
        overdue = elapsed > _PREDICTION_CYCLE_SECONDS

        if overdue:
            ring_color, center_text = "#ff6e6e", "overdue"
        elif pct > 0.75:
            ring_color, center_text = "#d1833d", _fmt_delta(remaining)
        else:
            ring_color, center_text = "#0e6d6e", _fmt_delta(remaining)
        degrees = pct * 360
        subtitle = f"{_fmt_delta(elapsed)} ago"
    else:
        # On-demand: full static ring, show age only
        degrees = 360
        ring_color = "#5f6f7f"
        center_text = _fmt_delta(elapsed)
        subtitle = "on demand"

    return f"""
    <div style="display:flex;flex-direction:column;align-items:center;gap:2px">
      <div style="
        width:68px;height:68px;border-radius:50%;
        background:conic-gradient({ring_color} {degrees}deg, #e0ddd4 {degrees}deg);
        display:flex;align-items:center;justify-content:center;
      ">
        <div style="
          width:52px;height:52px;border-radius:50%;
          background:#faf6ee;
          display:flex;align-items:center;justify-content:center;
          font-family:Manrope,sans-serif;font-weight:700;
          font-size:0.72rem;color:#17324d;
        ">{center_text}</div>
      </div>
      <span style="font-family:Manrope,sans-serif;font-size:0.65rem;
        color:#5f6f7f;text-align:center;line-height:1.1">
        {label}<br/>{subtitle}
      </span>
    </div>"""


_FRESHNESS_SOURCES: list[tuple[str, str, bool]] = [
    # (label, PromQL, scheduled?)
    (
        "Features",
        "foehncast_feature_pipeline_summary_generated_timestamp_seconds",
        True,
    ),
    (
        "Training",
        "foehncast_training_pipeline_summary_generated_timestamp_seconds",
        True,
    ),
    (
        "Prediction",
        "max(foehncast_prediction_log_latest_prediction_timestamp_seconds)",
        False,
    ),
]


@st.fragment(run_every=30)
def _render_freshness_bar() -> None:
    """Source-by-source circular indicators, auto-refreshed every 30 s.

    The three PromQL queries are fanned out in parallel so the sidebar
    render is bounded by the slowest single query, not the sum of all
    three. Important on Cloud Run + GMP where every query also pays a
    metadata-server bearer fetch.
    """
    cols = st.columns(len(_FRESHNESS_SOURCES))
    now = _time.time()
    exprs = [src[1] for src in _FRESHNESS_SOURCES]
    with ThreadPoolExecutor(max_workers=len(exprs)) as pool:
        values = list(pool.map(_prom_query, exprs))
    for col, (label, _expr, scheduled), ts in zip(cols, _FRESHNESS_SOURCES, values):
        with col:
            if ts is None:
                st.markdown(
                    f'<div style="text-align:center;opacity:0.4;'
                    f'font-size:0.75rem">{label}<br/>unavailable</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    _freshness_circle_html(label, now - ts, scheduled=scheduled),
                    unsafe_allow_html=True,
                )


def _render_sidebar_ml_panels() -> None:
    # --- Model Status (styled card with stats) -------------------------
    # Batch all sidebar PromQL queries in one parallel fan-out to eliminate
    # sequential round-trip latency (~100-200ms each on Cloud Run).
    _sidebar_exprs = [
        "foehncast_training_pipeline_registered_model_version",
        "foehncast_training_pipeline_evaluation_report_exists",
        "foehncast_training_pipeline_model_registered",
        'foehncast_training_pipeline_run_metric{metric_name="r2"}',
        'foehncast_training_pipeline_run_metric{metric_name="rmse"}',
        "foehncast_training_pipeline_feature_count",
        "foehncast_training_pipeline_row_count",
        "foehncast_hindcast_accuracy",
        "foehncast_hindcast_validated_count",
        'max(foehncast_drift_metric{metric_name="share_of_drifted_columns"})',
    ]
    (
        model_ver,
        eval_ok,
        reg_ok,
        r2_val,
        rmse_val,
        feat_count,
        train_rows,
        hindcast_acc,
        hindcast_n,
        drift_share,
    ) = _prom_query_batch(_sidebar_exprs)

    verified = (eval_ok is not None and eval_ok >= 1) and (
        reg_ok is not None and reg_ok >= 1
    )
    ver_label = f"v{int(model_ver)}" if model_ver is not None else "—"
    # Show "—" when no validated pairs exist (avoids misleading "0%")
    if hindcast_n is not None and hindcast_n < 1:
        hindcast_acc = None
    # Confidence = 1 - share of features whose drift_detected fired.
    # Per-column drift_score is on different scales (PSI, Wasserstein, ...)
    # and can saturate at 1.0, which used to collapse confidence to 0 %.
    confidence = (
        max(0.0, min(1.0, 1.0 - drift_share)) if drift_share is not None else None
    )

    if verified:
        badge_color = "var(--accent)"
        badge_bg = "var(--accent-soft)"
        badge_text = "Verified ✓"
    else:
        badge_color = "#c0392b"
        badge_bg = "rgba(192, 57, 43, 0.10)"
        badge_text = "Unverified ✗"

    def _stat(label: str, value: float | None, fmt: str = ".2f") -> str:
        display = f"{value:{fmt}}" if value is not None else "—"
        return (
            '<div style="display:flex;align-items:baseline;'
            "justify-content:space-between;gap:8px;padding:4px 0;"
            'border-bottom:1px solid rgba(23,50,77,0.06)">'
            f'<span style="font-family:Manrope,sans-serif;'
            "font-size:0.62rem;font-weight:700;letter-spacing:0.04em;"
            f'text-transform:uppercase;color:var(--muted)">{label}</span>'
            f'<strong style="font-family:Newsreader,serif;'
            f'font-size:0.95rem;color:var(--ink)">{display}</strong></div>'
        )

    stats_html = (
        '<div style="margin-top:10px;padding-top:8px;'
        'border-top:1px solid rgba(23,50,77,0.08)">'
        + _stat("Confidence", confidence, ".0%")
        + _stat("R²", r2_val)
        + _stat("RMSE", rmse_val)
        + _stat("Hindcast", hindcast_acc, ".0%")
        + _stat("Features", feat_count, ".0f")
        + _stat("Rows", train_rows, ".0f")
        + "</div>"
    )

    st.markdown(
        f"""
        <div style="
          border: 1px solid var(--line);
          border-radius: 20px;
          background: var(--panel);
          box-shadow: var(--shadow);
          padding: 16px 18px;
          margin-bottom: 0.6rem;
        ">
          <p class="eyebrow" style="margin:0 0 6px">Champion Model</p>
          <div style="display:flex;align-items:baseline;gap:10px">
            <span style="
              font-family:'Newsreader',serif;
              font-size:1.8rem;
              font-weight:700;
              color:var(--ink);
              line-height:1;
            ">{ver_label}</span>
            <span style="
              font-family:'Manrope',sans-serif;
              font-size:0.75rem;
              font-weight:700;
              color:{badge_color};
              background:{badge_bg};
              border-radius:12px;
              padding:3px 10px;
              letter-spacing:0.02em;
            ">{badge_text}</span>
          </div>
          {stats_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_spot_map(ranked_spots: list[dict[str, Any]]) -> None:
    """Render a map showing every spot plus the rider home."""
    spots_cfg = get_spots()
    coord_lookup = {s["id"]: (float(s["lat"]), float(s["lon"])) for s in spots_cfg}
    rider = get_rider_config()
    home_lat = float(rider["home_lat"])
    home_lon = float(rider["home_lon"])

    spot_points: list[dict[str, Any]] = []
    for rank, spot in enumerate(ranked_spots, start=1):
        coords = coord_lookup.get(spot["spot_id"])
        if coords is None:
            continue
        lat, lon = coords
        spot_points.append(
            {
                "lat": lat,
                "lon": lon,
                "name": spot["spot_name"],
                "rank": rank,
                "quality_label": spot["quality_label"],
            }
        )

    home_point = [{"lat": home_lat, "lon": home_lon, "name": "Rider home"}]

    if not spot_points:
        return

    try:
        import pydeck as pdk
    except ImportError:
        # Fallback: simple Streamlit map with a single layer
        frame = pd.DataFrame(spot_points + home_point)
        st.markdown('<p class="eyebrow">Spot map</p>', unsafe_allow_html=True)
        st.map(frame[["lat", "lon"]], zoom=7)
        return

    lats = [p["lat"] for p in spot_points] + [home_lat]
    lons = [p["lon"] for p in spot_points] + [home_lon]
    center_lat = (min(lats) + max(lats)) / 2
    center_lon = (min(lons) + max(lons)) / 2

    spot_layer = pdk.Layer(
        "ScatterplotLayer",
        data=spot_points,
        get_position="[lon, lat]",
        get_fill_color=[14, 138, 134, 220],
        get_radius=3500,
        pickable=True,
        stroked=True,
        get_line_color=[7, 37, 42, 255],
        line_width_min_pixels=1,
    )
    home_layer = pdk.Layer(
        "ScatterplotLayer",
        data=home_point,
        get_position="[lon, lat]",
        get_fill_color=[255, 122, 38, 240],
        get_radius=4500,
        pickable=True,
        stroked=True,
        get_line_color=[7, 37, 42, 255],
        line_width_min_pixels=1,
    )
    label_layer = pdk.Layer(
        "TextLayer",
        data=spot_points + home_point,
        get_position="[lon, lat]",
        get_text="name",
        get_size=14,
        get_color=[7, 37, 42, 255],
        get_alignment_baseline="'bottom'",
        get_pixel_offset=[0, -12],
    )

    view = pdk.ViewState(
        latitude=center_lat,
        longitude=center_lon,
        zoom=7,
        pitch=0,
    )
    deck = pdk.Deck(
        layers=[spot_layer, home_layer, label_layer],
        initial_view_state=view,
        map_style="light",
        tooltip={"text": "{name}"},
    )

    st.markdown(
        '<div style="margin-top:1rem"></div>',
        unsafe_allow_html=True,
    )
    st.pydeck_chart(deck, use_container_width=True)


@st.fragment
def _render_rider_console(
    dashboard_data: dict[str, Any],
    selected_spot_ids: list[str],
    spot_lookup: dict[str, dict[str, Any]],
) -> None:
    ranked_spots = dashboard_data["ranked_spots"]

    # --- Focus timeline (full width, past + future) ----------------------
    focus_spot_ids = [spot["spot_id"] for spot in ranked_spots] or selected_spot_ids
    default_focus = focus_spot_ids[0] if focus_spot_ids else None
    if "rider_focus_spot" not in st.session_state or (
        st.session_state["rider_focus_spot"] not in focus_spot_ids
    ):
        st.session_state["rider_focus_spot"] = default_focus

    focus_spot_id = st.session_state.get("rider_focus_spot") or default_focus

    if focus_spot_id is not None:
        timeline_frame = _focus_spot_timeline(focus_spot_id)
        st.subheader(f"Wind speed — {_spot_label(spot_lookup, focus_spot_id)}")
        if timeline_frame.empty:
            st.info("No timeline data available for this spot right now.")
        else:
            tz = timeline_frame["time"].dt.tz
            now_ts = pd.Timestamp.now(tz=tz) if tz is not None else pd.Timestamp.now()
            kn_to_kmh = 1.852
            threshold_kmh = 12.0 * kn_to_kmh  # ~22.2 km/h
            elevation_order = ["10m", "80m", "120m"]
            elevations_present = [
                e for e in elevation_order if e in timeline_frame["elevation"].unique()
            ]

            # Dim past region: a faint rectangle from the earliest sample to now.
            past_min = timeline_frame["time"].min()
            past_band = pd.DataFrame({"x": [past_min], "x2": [now_ts]})
            past_rect = (
                alt.Chart(past_band)
                .mark_rect(color="#07252a", opacity=0.07)
                .encode(x="x:T", x2="x2:T")
            )

            # Night rectangles (~18:00–06:00 local) for diurnal context.
            t_min = timeline_frame["time"].min()
            t_max = timeline_frame["time"].max()
            night_start = t_min.normalize() - pd.Timedelta(days=1)
            nights: list[dict[str, pd.Timestamp]] = []
            day = night_start
            while day <= t_max.normalize() + pd.Timedelta(days=1):
                nights.append(
                    {
                        "x": day + pd.Timedelta(hours=18),
                        "x2": day + pd.Timedelta(days=1, hours=6),
                    }
                )
                day = day + pd.Timedelta(days=1)
            night_frame = pd.DataFrame(nights)
            night_rect = (
                alt.Chart(night_frame)
                .mark_rect(color="#07252a", opacity=0.10)
                .encode(x="x:T", x2="x2:T")
            )

            # Day/night cosine reference line: peaks at local noon, trough at midnight.
            diurnal_idx = pd.date_range(
                t_min.floor("h"), t_max.ceil("h"), freq="30min", tz=tz
            )
            max_wind = float(timeline_frame["wind_speed"].max() or 0.0)
            amplitude = max(max_wind * 0.9, threshold_kmh)
            diurnal_frame = pd.DataFrame(
                {
                    "time": diurnal_idx,
                    "value": [
                        amplitude
                        * (
                            0.5
                            + 0.5
                            * math.cos(
                                2 * math.pi * ((ts.hour + ts.minute / 60.0) - 12) / 24.0
                            )
                        )
                        for ts in diurnal_idx
                    ],
                }
            )
            diurnal_line = (
                alt.Chart(diurnal_frame)
                .mark_line(
                    color="#e0a500",
                    opacity=0.45,
                    strokeDash=[2, 4],
                    strokeWidth=1.5,
                    interpolate="monotone",
                )
                .encode(x="time:T", y="value:Q")
            )

            lines = (
                alt.Chart(timeline_frame)
                .mark_line(interpolate="monotone", strokeWidth=2.2)
                .encode(
                    x=alt.X("time:T", title="Time"),
                    y=alt.Y(
                        "wind_speed:Q",
                        title="Wind speed (km/h)",
                    ),
                    color=alt.Color(
                        "elevation:N",
                        scale=alt.Scale(
                            domain=elevations_present,
                            range=["#3b5a5a", "#0e8a86", "#ff7a26"][
                                : len(elevations_present)
                            ],
                        ),
                        legend=alt.Legend(title="Elevation", orient="top"),
                    ),
                )
            )
            threshold = (
                alt.Chart(pd.DataFrame({"y": [threshold_kmh]}))
                .mark_rule(color="#c0392b", strokeDash=[4, 4], strokeWidth=1.5)
                .encode(y="y:Q")
            )
            threshold_label = (
                alt.Chart(
                    pd.DataFrame(
                        {
                            "y": [threshold_kmh],
                            "label": ["12 kn rideable"],
                        }
                    )
                )
                .mark_text(
                    align="left",
                    baseline="bottom",
                    dx=6,
                    dy=-3,
                    color="#c0392b",
                    fontSize=10,
                )
                .encode(y="y:Q", text="label:N")
                .transform_calculate(x="datum.x")
            )
            now_rule = (
                alt.Chart(pd.DataFrame({"x": [now_ts]}))
                .mark_rule(color="#ff7a26", strokeWidth=2)
                .encode(x="x:T")
            )
            st.altair_chart(
                (
                    night_rect
                    + past_rect
                    + diurnal_line
                    + lines
                    + threshold
                    + threshold_label
                    + now_rule
                )
                .properties(height=300, background="transparent")
                .configure_view(strokeWidth=0, fill=None)
                .configure_axis(
                    domainColor="#3b5a5a",
                    gridColor="rgba(7, 37, 42, 0.10)",
                    labelColor="#07252a",
                    titleColor="#07252a",
                ),
                use_container_width=True,
            )

        # Spot switcher buttons (one per ranked spot) — equal width, blank lead column
        n = len(focus_spot_ids)
        if n:
            # Lead column weight is shared between the button row and the
            # transposed metrics grid so spot columns line up under each button.
            lead_weight = 0.9
            button_cols = st.columns([lead_weight] + [1] * n)
            for index, spot_id in enumerate(focus_spot_ids):
                spot = spot_lookup[spot_id]
                button_label = spot["name"]
                is_active = spot_id == focus_spot_id
                if button_cols[index + 1].button(
                    button_label,
                    key=f"focus_spot_{spot_id}",
                    use_container_width=True,
                    type="primary" if is_active else "secondary",
                ):
                    st.session_state["rider_focus_spot"] = spot_id
                    # Scope the rerun to this fragment so the System tab
                    # stays mounted and doesn't reload.
                    st.rerun(scope="fragment")

            # Transposed metrics grid: a CSS grid with the same column ratios
            # and gap as the button row above, so column centers line up.
            metric_rows: list[tuple[str, list[str]]] = [
                ("Signal", [s["quality_label"] for s in ranked_spots]),
                (
                    "Peak quality",
                    [f"{float(s['quality_index']):.2f}" for s in ranked_spots],
                ),
                (
                    "Rideable hrs",
                    [f"{int(s['rideable_hours'])}" for s in ranked_spots],
                ),
                (
                    "Drive min",
                    [f"{float(s['drive_minutes']):.1f}" for s in ranked_spots],
                ),
                (
                    "Session hrs",
                    [f"{float(s['session_hours']):.1f}" for s in ranked_spots],
                ),
                (
                    "Ride/drive",
                    [f"{float(s['ride_drive_ratio']):.2f}" for s in ranked_spots],
                ),
                ("Score", [f"{float(s['score']):.3f}" for s in ranked_spots]),
            ]
            grid_cols = f"{lead_weight}fr " + " ".join(["1fr"] * n)
            lead_cells = "".join(
                f'<div class="cell">{label}</div>' for label, _ in metric_rows
            )
            spot_cols_html: list[str] = []
            for col_idx, spot in enumerate(ranked_spots):
                active_cls = " active" if spot["spot_id"] == focus_spot_id else ""
                cells = "".join(
                    f'<div class="cell">{values[col_idx]}</div>'
                    for _, values in metric_rows
                )
                spot_cols_html.append(
                    f'<div class="col spot{active_cls}">{cells}</div>'
                )
            st.markdown(
                f'<div class="ranked-stack" style="grid-template-columns:{grid_cols}">'
                f'<div class="col lead">{lead_cells}</div>'
                + "".join(spot_cols_html)
                + "</div>",
                unsafe_allow_html=True,
            )

    st.divider()

    _render_spot_map(ranked_spots)


# ---------------------------------------------------------------------------
# System tab — pipelines panel (PromQL-driven).
#
# Layout, per pipeline (feature / training / inference), in a single column:
#   [ Header strip ] pipeline name · status pill · summary age
#   [ Body row     ] left=step pills with state+duration · right=live log view
#   [ Footer row   ] compact metric chips
# A small top toolbar above the rails owns the cascade and per-job triggers.
# ---------------------------------------------------------------------------


_PIPELINE_RAILS: list[dict[str, Any]] = [
    {
        "key": "feature",
        "title": "Feature pipeline",
        "job_name_key": "feature",
        "success_metric": "foehncast_feature_pipeline_run_success",
        "summary_ts_metric": "foehncast_feature_pipeline_summary_generated_timestamp_seconds",
        "stages_query": ('foehncast_feature_pipeline_stage_state{dataset="forecast"}'),
        "stage_duration_query": (
            'foehncast_feature_pipeline_stage_duration_seconds{dataset="forecast"}'
        ),
        "stage_order": ["fetch", "engineer", "validate", "store"],
        "metric_chips": [
            ("stored spots", "foehncast_feature_pipeline_stored_spot_count", "int"),
            ("drifted", "foehncast_feature_pipeline_drifted_spot_count", "int"),
            ("failed", "foehncast_feature_pipeline_failed_spot_count", "int"),
            (
                "dataset drift",
                "foehncast_feature_pipeline_dataset_drift_detected",
                "bool",
            ),
            ("ingest rows", "foehncast_feature_pipeline_spot_ingest_rows", "int"),
        ],
    },
    {
        "key": "training",
        "title": "Training pipeline",
        "job_name_key": "training",
        "success_metric": "foehncast_training_pipeline_run_success",
        "summary_ts_metric": "foehncast_training_pipeline_summary_generated_timestamp_seconds",
        "stages_query": (
            'foehncast_training_pipeline_stage_state{requested_stage="Production"}'
        ),
        "stage_duration_query": (
            'foehncast_training_pipeline_stage_duration_seconds{requested_stage="Production"}'
        ),
        "stage_order": ["train", "evaluate", "register"],
        "metric_chips": [
            ("rows", "foehncast_training_pipeline_row_count", "int"),
            ("features", "foehncast_training_pipeline_feature_count", "int"),
            ("R²", 'foehncast_training_pipeline_run_metric{metric_name="r2"}', "f2"),
            (
                "RMSE",
                'foehncast_training_pipeline_run_metric{metric_name="rmse"}',
                "f3",
            ),
            (
                "model",
                "foehncast_training_pipeline_registered_model_version",
                "version",
            ),
        ],
    },
    {
        "key": "inference",
        "title": "Inference pipeline",
        "job_name_key": "inference",
        "success_metric": None,
        "summary_ts_metric": "foehncast_prediction_log_latest_prediction_timestamp_seconds",
        "stages_query": None,
        "stage_duration_query": None,
        "stage_order": [],
        "metric_chips": [
            ("predictions", "foehncast_prediction_log_total_row_count", "int"),
            ("models", "foehncast_prediction_log_model_count", "int"),
            (
                "hindcast",
                "foehncast_hindcast_accuracy",
                "pct",
            ),
            (
                "confidence",
                'clamp_max(1 - max(foehncast_drift_metric{metric_name="share_of_drifted_columns"}), 1)',
                "pct",
            ),
        ],
    },
]


def _stage_index(rail: dict[str, Any]) -> dict[str, dict[str, float]]:
    """Return ``{stage_name: {state, duration}}`` for a rail in one fan-out."""
    out: dict[str, dict[str, float]] = {
        stage: {"state": float("nan"), "duration": float("nan")}
        for stage in rail["stage_order"]
    }
    if rail.get("stages_query"):
        for entry in _prom_query_vector(rail["stages_query"]):
            stage = entry["labels"].get("stage")
            if stage in out:
                out[stage]["state"] = entry["value"]
    if rail.get("stage_duration_query"):
        for entry in _prom_query_vector(rail["stage_duration_query"]):
            stage = entry["labels"].get("stage")
            if stage in out:
                out[stage]["duration"] = entry["value"]
    return out


def _stage_pill_html(name: str, state: float, duration: float) -> str:
    """Render a single nested step pill (name + state dot + duration)."""
    if state != state:  # NaN
        bg, fg, dot, label = "#eef3ee", "#3b5a5a", "#9aa5a5", "—"
    elif state >= 0.999:
        bg, fg, dot, label = "rgba(14, 138, 134, 0.14)", "#07252a", "#0e8a86", "ok"
    elif state <= -0.5:
        bg, fg, dot, label = "rgba(192, 57, 43, 0.10)", "#c0392b", "#c0392b", "fail"
    else:
        bg, fg, dot, label = "rgba(255, 122, 38, 0.14)", "#7a3f10", "#ff7a26", "running"
    dur_text = (
        f"{duration:.2f}s"
        if (duration == duration and duration < 60)
        else (f"{duration / 60:.1f}m" if duration == duration else "—")
    )
    return (
        f'<div style="display:flex;align-items:center;gap:8px;'
        f"padding:6px 12px;border-radius:999px;background:{bg};color:{fg};"
        f'font-family:Manrope,sans-serif;font-size:0.78rem;font-weight:600">'
        f'<span style="width:8px;height:8px;border-radius:50%;background:{dot}"></span>'
        f"<span>{name}</span>"
        f'<span style="color:#5f6f7f;font-weight:500;font-size:0.72rem">{label} · {dur_text}</span>'
        "</div>"
    )


def _chip_value(expr: str, kind: str) -> str:
    """Format a chip's value from an instant PromQL gauge."""
    value = _prom_query(expr)
    return _format_chip(value, kind)


def _format_chip(value: float | None, kind: str) -> str:
    """Format a pre-fetched chip value."""
    if value is None:
        return "—"
    if kind == "int":
        return f"{int(value)}"
    if kind == "f2":
        return f"{value:.2f}"
    if kind == "f3":
        return f"{value:.3f}"
    if kind == "pct":
        return f"{value * 100:.0f} %"
    if kind == "version":
        return f"v{int(value)}"
    if kind == "bool":
        return "drift" if value >= 0.5 else "clean"
    return f"{value:g}"


def _status_pill_html(success: float | None, summary_ts: float | None) -> str:
    if success is None and summary_ts is None:
        bg, fg, text = "#eef3ee", "#3b5a5a", "no data"
    elif success is None:
        bg, fg, text = "rgba(14, 138, 134, 0.14)", "#07252a", "live"
    elif success >= 0.5:
        bg, fg, text = "rgba(14, 138, 134, 0.16)", "#0e8a86", "last run ok"
    else:
        bg, fg, text = "rgba(192, 57, 43, 0.12)", "#c0392b", "last run failed"
    age = (
        f"{_fmt_delta(_time.time() - summary_ts)} ago"
        if (summary_ts is not None and summary_ts > 0)
        else "no summary yet"
    )
    return (
        f'<div style="display:flex;align-items:center;gap:10px;'
        'font-family:Manrope,sans-serif;font-size:0.78rem">'
        f'<span style="padding:3px 10px;border-radius:999px;background:{bg};'
        f'color:{fg};font-weight:700">{text}</span>'
        f'<span style="color:#5f6f7f">{age}</span>'
        "</div>"
    )


def _render_log_panel(job_name: str) -> None:
    """Render the latest 6 Cloud Logging entries for a job."""
    logs = _list_job_logs(job_name, limit=6)
    if not logs:
        st.markdown(
            '<div style="font-family:Manrope,sans-serif;font-size:0.72rem;'
            "color:#5f6f7f;padding:8px 12px;background:rgba(7,37,42,0.04);"
            'border-radius:8px">no recent log entries</div>',
            unsafe_allow_html=True,
        )
        return
    sev_color = {
        "DEFAULT": "#5f6f7f",
        "DEBUG": "#5f6f7f",
        "INFO": "#0e8a86",
        "NOTICE": "#0e8a86",
        "WARNING": "#ff7a26",
        "ERROR": "#c0392b",
        "CRITICAL": "#c0392b",
        "ALERT": "#c0392b",
        "EMERGENCY": "#c0392b",
    }
    lines_html: list[str] = []
    for entry in logs:
        ts = (
            entry["timestamp"][11:19]
            if len(entry["timestamp"]) >= 19
            else entry["timestamp"]
        )
        color = sev_color.get(entry["severity"], "#5f6f7f")
        msg = entry["message"]
        if len(msg) > 160:
            msg = msg[:157] + "…"
        # Escape angle brackets to keep HTML safe.
        msg_safe = msg.replace("<", "&lt;").replace(">", "&gt;")
        lines_html.append(
            f'<div style="display:flex;gap:8px;align-items:baseline;padding:2px 0">'
            f'<span style="color:#5f6f7f;font-size:0.66rem;min-width:54px">{ts}</span>'
            f'<span style="color:{color};font-size:0.62rem;font-weight:700;min-width:54px">{entry["severity"]}</span>'
            f'<span style="color:#07252a;font-size:0.72rem;font-family:ui-monospace,SFMono-Regular,Menlo,monospace">{msg_safe}</span>'
            "</div>"
        )
    st.markdown(
        '<div style="max-height:170px;overflow-y:auto;padding:10px 12px;'
        "background:rgba(7,37,42,0.03);border-radius:8px;"
        'border:1px solid rgba(7,37,42,0.08)">' + "".join(lines_html) + "</div>",
        unsafe_allow_html=True,
    )


def _render_pipeline_rail(rail: dict[str, Any], prefetched: dict[str, Any]) -> None:
    """Render one pipeline as a horizontal rail: header / body / metrics.

    *prefetched* contains ``success``, ``summary_ts``, and ``chip_values``
    already resolved by the batched fan-out in _render_pipelines_panel.
    """
    success = prefetched["success"]
    summary_ts = prefetched["summary_ts"]

    # Header strip
    header_cols = st.columns([0.55, 0.45])
    with header_cols[0]:
        st.markdown(
            f'<div style="font-family:Manrope,sans-serif;font-weight:800;'
            f'font-size:0.95rem;color:#07252a;letter-spacing:0.01em">{rail["title"]}</div>',
            unsafe_allow_html=True,
        )
    with header_cols[1]:
        st.markdown(_status_pill_html(success, summary_ts), unsafe_allow_html=True)

    # Body: left = step pills, right = log preview
    body_cols = st.columns([0.55, 0.45], gap="medium")
    with body_cols[0]:
        if rail["stage_order"]:
            stages = _stage_index(rail)
            pills_html = "".join(
                _stage_pill_html(name, stages[name]["state"], stages[name]["duration"])
                for name in rail["stage_order"]
            )
            st.markdown(
                '<div style="display:flex;flex-wrap:wrap;gap:8px;padding:6px 0">'
                + pills_html
                + "</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div style="font-family:Manrope,sans-serif;font-size:0.78rem;'
                'color:#5f6f7f;padding:6px 0">no stage metrics — see logs →</div>',
                unsafe_allow_html=True,
            )
    with body_cols[1]:
        _render_log_panel(_PIPELINE_JOB_NAMES[rail["job_name_key"]])

    # Footer: metric chips (values already resolved by batch fan-out)
    chip_parts: list[str] = []
    for (label, _expr, kind), value in zip(
        rail["metric_chips"], prefetched["chip_values"]
    ):
        display = _format_chip(value, kind)
        chip_parts.append(
            f'<div style="display:flex;flex-direction:column;align-items:flex-start;'
            "padding:6px 12px;background:rgba(7,37,42,0.04);border-radius:8px;"
            'min-width:90px">'
            f'<span style="font-family:Manrope,sans-serif;font-size:0.62rem;'
            "font-weight:700;letter-spacing:0.04em;text-transform:uppercase;"
            f'color:#5f6f7f">{label}</span>'
            f'<strong style="font-family:Newsreader,serif;font-size:1rem;color:#07252a">{display}</strong>'
            "</div>"
        )
    st.markdown(
        '<div style="display:flex;flex-wrap:wrap;gap:8px;padding-top:6px;padding-bottom:6px">'
        + "".join(chip_parts)
        + "</div>",
        unsafe_allow_html=True,
    )


def _render_pipelines_panel() -> None:
    """System tab body: triggers, three pipeline rails, recent executions.

    Every visible value is fed by an instant PromQL
    query against the serve container's mini engine, plus a Cloud
    Logging tail per pipeline.

    All scalar PromQL queries for all three rails are batched into a single
    parallel fan-out to eliminate sequential round-trip latency.
    """
    triggers_available = bool(_WORKFLOWS_PROJECT and _WORKFLOWS_REGION)

    # Top toolbar -----------------------------------------------------
    toolbar = st.columns([1.2, 4])
    cascade_clicked = toolbar[0].button(
        "DO NOT CLICK",
        type="primary",
        disabled=not triggers_available,
        help="Cloud Workflows: feature → training → inference",
        key="pipe_trigger_cascade",
    )

    if cascade_clicked:
        name = _trigger_pipeline()
        st.success(f"Cascade started: {name.rsplit('/', 1)[-1]}") if name else st.error(
            "Failed to start cascade"
        )
        _list_workflow_executions.clear()

    if not triggers_available:
        st.caption(
            "Triggers and logs require GCP_PROJECT_ID / GCP_LOCATION — available "
            "on the Cloud Run UI service."
        )

    # Pre-fetch ALL scalar metrics for all rails in one parallel batch.
    # This replaces ~15 sequential HTTP round-trips with one fan-out.
    all_scalar_exprs: list[str] = []
    expr_map: list[tuple[int, str]] = []  # (rail_index, "success"|"summary"|chip_idx)
    for rail_idx, rail in enumerate(_PIPELINE_RAILS):
        if rail.get("success_metric"):
            all_scalar_exprs.append(rail["success_metric"])
            expr_map.append((rail_idx, "success"))
        if rail.get("summary_ts_metric"):
            all_scalar_exprs.append(rail["summary_ts_metric"])
            expr_map.append((rail_idx, "summary"))
        for chip_idx, (_label, expr, _kind) in enumerate(rail["metric_chips"]):
            all_scalar_exprs.append(expr)
            expr_map.append((rail_idx, f"chip_{chip_idx}"))

    batch_results = _prom_query_batch(all_scalar_exprs) if all_scalar_exprs else []

    # Distribute results back to per-rail structures.
    rail_data: list[dict[str, Any]] = [
        {"success": None, "summary_ts": None, "chip_values": []}
        for _ in _PIPELINE_RAILS
    ]
    for (rail_idx, key), value in zip(expr_map, batch_results):
        if key == "success":
            rail_data[rail_idx]["success"] = value
        elif key == "summary":
            rail_data[rail_idx]["summary_ts"] = value
        elif key.startswith("chip_"):
            rail_data[rail_idx]["chip_values"].append(value)

    # Pipeline rails -------------------------------------------------
    for index, rail in enumerate(_PIPELINE_RAILS):
        if index > 0:
            st.markdown(
                '<hr style="border:none;border-top:1px solid rgba(7,37,42,0.10);'
                'margin:14px 0">',
                unsafe_allow_html=True,
            )
        _render_pipeline_rail(rail, rail_data[index])

    # Recent cascade executions -------------------------------------
    st.markdown(
        '<div style="font-family:Manrope,sans-serif;font-weight:700;'
        "font-size:0.78rem;letter-spacing:0.04em;text-transform:uppercase;"
        'color:#5f6f7f;padding:18px 0 6px 0">Recent cascade executions</div>',
        unsafe_allow_html=True,
    )
    executions = _list_workflow_executions(limit=5) if triggers_available else []
    if executions:
        rows = []
        now = _time.time()
        for ex in executions:
            name = ex.get("name", "").rsplit("/", 1)[-1]
            state = ex.get("state", "—")
            start_iso = ex.get("startTime", "")
            try:
                started = pd.to_datetime(start_iso, utc=True).timestamp()
                age = _fmt_delta(now - started)
            except Exception:
                age = "—"
            rows.append({"Execution": name, "State": state, "Started": age})
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    else:
        st.caption("No cascade executions visible yet.")


@st.fragment
def _render_system_tab() -> None:
    """System tab: pipelines panel, lazy loaded to keep the rider tab fast.

    Streamlit executes every tab body on every script run, so any work done
    here also blocks the rider tab. We gate the PromQL fan-out and the
    Workflows ListExecutions call behind an explicit click.
    """
    if not st.session_state.get("system_tab_loaded"):
        st.info(
            "Pipelines panel loads on demand to keep the rider tab fast. "
            "Click below to load it — it stays loaded for the rest of "
            "this session."
        )
        if st.button("Load pipelines panel", type="primary"):
            st.session_state["system_tab_loaded"] = True
            st.rerun(scope="fragment")
        return

    _render_pipelines_panel()


def main() -> None:
    _inject_styles()

    available_spots = _available_spots()
    spot_lookup = {spot["id"]: spot for spot in available_spots}
    all_spot_ids = [spot["id"] for spot in available_spots]

    dashboard_data: dict[str, Any] | None = None
    dashboard_error: Exception | None = None
    try:
        with st.spinner(
            "Loading forecasts, drive times, and ranked recommendations..."
        ):
            dashboard_data = _live_dashboard_data(tuple(all_spot_ids))
    except Exception as exc:
        dashboard_error = exc

    with st.sidebar:
        st.markdown(
            """
            <p class="eyebrow" style="margin-top:0">FoehnCast</p>
            <p class="hero-lede">
              One rider profile, six Swiss spots, one served model. Ranked recommendations
              combine live Open-Meteo forecasts, engineered wind features, drive-time estimates,
              and the current champion model through the same inference path the API serves.
            </p>
            """,
            unsafe_allow_html=True,
        )
        if dashboard_data is not None:
            st.markdown(
                _profile_card(dashboard_data["rider_profile"]),
                unsafe_allow_html=True,
            )
            st.caption(
                "Drive-time ranking uses the rider home from config.yaml and live OSRM route estimates."
            )
        st.markdown('<div style="margin-top:1.2rem"></div>', unsafe_allow_html=True)
        _render_freshness_bar()
        st.divider()
        _render_sidebar_ml_panels()

    rider_tab, system_tab = st.tabs(["Rider Console", "System"])

    with rider_tab:
        if dashboard_error is not None:
            st.error(
                "Could not load the current forecast and model stack. Check MLflow, "
                "network access, and the configured serving model alias."
            )
            st.exception(dashboard_error)
        elif dashboard_data is not None:
            _render_rider_console(dashboard_data, all_spot_ids, spot_lookup)

    with system_tab:
        _render_system_tab()


main()
