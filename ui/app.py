"""Streamlit rider console for FoehnCast spot recommendations."""

from __future__ import annotations

import json
import os
import time as _time
import urllib.request
from typing import Any
from urllib.parse import quote as urlquote
from urllib.parse import urlencode

import streamlit as st

import altair as alt
import pandas as pd

from foehncast.config import get_model_config, get_rider_config, get_spots
from foehncast.feature_pipeline.engineer import engineer_features
from foehncast.feature_pipeline.ingest import fetch_forecast
from foehncast.inference_pipeline.dashboard import (
    list_dashboard_spots,
    load_dashboard_data,
)
from foehncast.inference_pipeline.predict import (
    get_serving_model_alias,
)
from foehncast.training_pipeline.register import get_model_by_alias

st.set_page_config(
    page_title="FoehnCast Rider Console",
    layout="wide",
    initial_sidebar_state="expanded",
)

_RIDER_GRAFANA = {
    "title": "Live Conditions",
    "description": (
        "Rider-facing conditions, spot health, and drift posture from the "
        "Grafana rider dashboard."
    ),
    "uid": "foehncast-rider",
    "slug": "foehncast-rider",
    "from": "now-12h",
    "refresh": "30s",
    "height": 1560,
}
_PIPELINE_GRAFANA = {
    "tab": "Pipeline",
    "title": "Pipeline",
    "description": (
        "Operations view for service health, feature and training stages, "
        "freshness, and inference SLIs."
    ),
    "uid": "foehncast-operations",
    "slug": "foehncast-operations",
    "from": "now-24h",
    "refresh": "30s",
    "height": 1840,
}
_ML_DASHBOARD_UID = "foehncast-ml-diagnostics"
_ML_DASHBOARD_SLUG = "foehncast-ml-diagnostics"
_TRUTHY_VALUES = {"1", "true", "yes", "on"}

_PROMETHEUS_BASE_URL = os.getenv(
    "FOEHNCAST_PROMETHEUS_URL", "http://127.0.0.1:9090"
).rstrip("/")

_WORKFLOWS_PROJECT = os.getenv("GCP_PROJECT_ID", "")
_WORKFLOWS_REGION = os.getenv("GCP_LOCATION", "")
_WORKFLOWS_NAME = os.getenv("FOEHNCAST_WORKFLOW_NAME", "foehncast-pipeline-cascade")


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


@st.cache_data(show_spinner=False)
def _available_spots() -> list[dict[str, Any]]:
    return list_dashboard_spots()


@st.cache_resource(show_spinner=False)
def _champion_model(alias: str) -> Any:
    """Load the champion model once per process; switch only on alias change."""
    return get_model_by_alias(alias)


@st.cache_data(ttl=900, show_spinner=False)
def _live_dashboard_data(selected_spot_ids: tuple[str, ...]) -> dict[str, Any]:
    return load_dashboard_data(list(selected_spot_ids) if selected_spot_ids else None)


@st.cache_data(ttl=900, show_spinner=False)
def _focus_spot_timeline(spot_id: str, *, past_days: int = 1) -> pd.DataFrame:
    """Past+future predicted quality_index for a single spot.

    Open-Meteo's forecast endpoint, called with ``past_days``, returns
    observed/analysed hours before now and the standard forecast horizon
    afterwards. We run the served champion model across that combined
    window so the rider sees how predicted conditions line up against
    what the weather has actually done in the last hours.
    """
    spot = next((s for s in get_spots() if s["id"] == spot_id), None)
    if spot is None:
        return pd.DataFrame(columns=["time", "quality_index"])

    forecast_df = fetch_forecast(spot["lat"], spot["lon"], past_days=past_days)
    if forecast_df.empty:
        return pd.DataFrame(columns=["time", "quality_index"])

    feature_columns = get_model_config()["features"]
    engineered_df = engineer_features(forecast_df, spot["shore_orientation_deg"])
    feature_frame = engineered_df[feature_columns].copy().ffill().bfill().fillna(0.0)
    model = _champion_model(get_serving_model_alias())
    predictions = model.predict(feature_frame)
    return pd.DataFrame(
        {
            "time": pd.to_datetime(engineered_df.index),
            "quality_index": [float(value) for value in predictions],
        }
    )


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


def _grafana_base_url() -> str:
    for key in ("FOEHNCAST_GRAFANA_BASE_URL", "GRAFANA_BASE_URL"):
        value = os.getenv(key, "").strip()
        if value:
            return value.rstrip("/")
    return "http://127.0.0.1:3000"


def _grafana_embedding_enabled() -> bool:
    return (
        os.getenv("FOEHNCAST_GRAFANA_ALLOW_EMBEDDING", "").strip().lower()
        in _TRUTHY_VALUES
    )


def _grafana_dashboard_url(
    uid: str, slug: str, *, from_range: str, refresh: str
) -> str:
    query = urlencode(
        {
            "orgId": 1,
            "theme": "dark",
            "from": from_range,
            "to": "now",
            "refresh": refresh,
        }
    )
    return f"{_grafana_base_url()}/d/{uid}/{slug}?{query}&kiosk"


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


def _grafana_solo_panel_url(
    uid: str,
    slug: str,
    panel_id: int,
    *,
    from_range: str = "now-24h",
    refresh: str | None = "30s",
    variables: dict[str, str] | None = None,
) -> str:
    """Build a Grafana solo-panel embed URL (no chrome, no branding).

    *variables* passes Grafana template variables, e.g.
    ``{"var-spot": "silvaplana", "var-dataset": "data"}``.

    Pass ``refresh=None`` (or empty string) to skip auto-refresh entirely;
    this avoids constant PromQL re-queries on static stat panels.
    """
    params: dict[str, str | int] = {
        "orgId": 1,
        "theme": "dark",
        "panelId": panel_id,
        "from": from_range,
        "to": "now",
        "hideLogo": "true",
    }
    if refresh:
        params["refresh"] = refresh
    if variables:
        params.update(variables)
    return f"{_grafana_base_url()}/d-solo/{uid}/{slug}?{urlencode(params)}"


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
    """Source-by-source circular indicators, auto-refreshed every 30 s."""
    cols = st.columns(len(_FRESHNESS_SOURCES))
    now = _time.time()
    for col, (label, expr, scheduled) in zip(cols, _FRESHNESS_SOURCES):
        with col:
            ts = _prom_query(expr)
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
    full_url = _grafana_dashboard_url(
        _ML_DASHBOARD_UID,
        _ML_DASHBOARD_SLUG,
        from_range="now-24h",
        refresh="30s",
    )

    # --- Model Status (styled card with stats) -------------------------
    model_ver = _prom_query("foehncast_training_pipeline_registered_model_version")
    eval_ok = _prom_query("foehncast_training_pipeline_evaluation_report_exists")
    reg_ok = _prom_query("foehncast_training_pipeline_model_registered")
    verified = (eval_ok is not None and eval_ok >= 1) and (
        reg_ok is not None and reg_ok >= 1
    )
    ver_label = f"v{int(model_ver)}" if model_ver is not None else "—"

    r2_val = _prom_query('foehncast_training_pipeline_run_metric{metric_name="r2"}')
    rmse_val = _prom_query('foehncast_training_pipeline_run_metric{metric_name="rmse"}')
    feat_count = _prom_query("foehncast_training_pipeline_feature_count")
    train_rows = _prom_query("foehncast_training_pipeline_row_count")
    hindcast_acc = _prom_query("foehncast_hindcast_accuracy")
    hindcast_n = _prom_query("foehncast_hindcast_validated_count")
    # Show "—" when no validated pairs exist (avoids misleading "0%")
    if hindcast_n is not None and hindcast_n < 1:
        hindcast_acc = None
    drift_max = _prom_query('max(foehncast_drift_metric{metric_name="drift_score"})')
    confidence = max(0.0, min(1.0, 1.0 - drift_max)) if drift_max is not None else None

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

    st.caption(f"[Full ML dashboard ↗]({full_url})")


def _render_timeline_panels() -> None:
    """Grafana timeseries panels shown above the tabs in the main area."""
    if not _grafana_embedding_enabled():
        return

    col_a, col_b = st.columns(2)
    with col_a:
        st.caption("Feature Drift Score")
        url = _grafana_solo_panel_url(
            _ML_DASHBOARD_UID,
            _ML_DASHBOARD_SLUG,
            panel_id=505,
            from_range="now-24h",
            refresh="1m",
            variables={"var-dataset": "train"},
        )
        st.iframe(url, height=200)
    with col_b:
        st.caption("Model R²")
        url = _grafana_solo_panel_url(
            _ML_DASHBOARD_UID,
            _ML_DASHBOARD_SLUG,
            panel_id=513,
            from_range="now-24h",
            refresh="1m",
            variables={"var-dataset": "train"},
        )
        st.iframe(url, height=200)


def _render_monitoring_tab(config: dict[str, Any]) -> None:
    dashboard_url = _grafana_dashboard_url(
        config["uid"],
        config["slug"],
        from_range=config["from"],
        refresh=config["refresh"],
    )

    st.subheader(config["title"])
    st.caption(config["description"])
    st.markdown(f"[Open in Grafana]({dashboard_url})")

    if not _grafana_embedding_enabled():
        st.info(
            "Grafana embedding is disabled for this local run. Restart the local "
            "stack with FOEHNCAST_GRAFANA_ALLOW_EMBEDDING=true, or use "
            "./scripts/bootstrap-local.sh so the monitoring tabs can render inline."
        )
        return

    st.iframe(dashboard_url, height=config["height"])


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
        st.subheader(f"Focus timeline — {_spot_label(spot_lookup, focus_spot_id)}")
        if timeline_frame.empty:
            st.info("No timeline data available for this spot right now.")
        else:
            now_ts = pd.Timestamp.now(tz=timeline_frame["time"].dt.tz)
            chart_frame = timeline_frame.copy()
            chart_frame["phase"] = chart_frame["time"].apply(
                lambda ts: "Observed" if ts <= now_ts else "Forecast"
            )
            line = (
                alt.Chart(chart_frame)
                .mark_line(interpolate="monotone", strokeWidth=2.5)
                .encode(
                    x=alt.X("time:T", title="Time"),
                    y=alt.Y(
                        "quality_index:Q",
                        title="Quality index",
                        scale=alt.Scale(domain=[0, 5]),
                    ),
                    color=alt.Color(
                        "phase:N",
                        scale=alt.Scale(
                            domain=["Observed", "Forecast"],
                            range=["#3b5a5a", "#0e8a86"],
                        ),
                        legend=alt.Legend(title=None, orient="top"),
                    ),
                )
            )
            threshold = (
                alt.Chart(pd.DataFrame({"y": [2.0]}))
                .mark_rule(strokeDash=[4, 4], color="#1f5e44")
                .encode(y="y:Q")
            )
            now_rule = (
                alt.Chart(pd.DataFrame({"x": [now_ts]}))
                .mark_rule(color="#ff7a26", strokeWidth=2)
                .encode(x="x:T")
            )
            st.altair_chart(
                (line + threshold + now_rule)
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
                    st.rerun()

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


def _render_system_tab() -> None:
    """System tab: rider live conditions + operations + ML diagnostics dashboards."""
    _render_monitoring_tab(_RIDER_GRAFANA)
    st.divider()
    _render_monitoring_tab(_PIPELINE_GRAFANA)
    st.divider()
    _render_timeline_panels()
    st.divider()
    ml_config = {
        "title": "ML Diagnostics",
        "description": (
            "Drift analysis, training metrics, model registry status, "
            "and prediction monitoring."
        ),
        "uid": _ML_DASHBOARD_UID,
        "slug": _ML_DASHBOARD_SLUG,
        "from": "now-24h",
        "refresh": "30s",
        "height": 2200,
    }
    _render_monitoring_tab(ml_config)


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
        if _WORKFLOWS_PROJECT and _WORKFLOWS_REGION:
            st.divider()
            if st.button(
                "Run Pipeline",
                help="Trigger the feature → training → inference cascade in the cloud",
            ):
                execution_name = _trigger_pipeline()
                if execution_name:
                    st.success("Pipeline triggered")
                else:
                    st.error("Failed to trigger pipeline")
        st.caption(f"Grafana: {_grafana_base_url()}")

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
