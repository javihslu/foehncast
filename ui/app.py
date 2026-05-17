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

from foehncast.inference_pipeline.dashboard import (
    build_forecast_frame,
    build_ranking_frame,
    horizon_caption,
    list_dashboard_spots,
    load_dashboard_data,
)

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


@st.cache_data(show_spinner=False)
def _available_spots() -> list[dict[str, Any]]:
    return list_dashboard_spots()


@st.cache_data(ttl=900, show_spinner=False)
def _live_dashboard_data(selected_spot_ids: tuple[str, ...]) -> dict[str, Any]:
    return load_dashboard_data(list(selected_spot_ids) if selected_spot_ids else None)


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
          @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;600;700;800&family=Newsreader:opsz,wght@6..72,500;6..72,700&display=swap');

          :root {
            --bg: #f3eee2;
            --panel: rgba(255, 251, 244, 0.94);
            --panel-strong: rgba(255, 248, 237, 0.98);
            --ink: #17324d;
            --muted: #5f6f7f;
            --accent: #0e6d6e;
            --accent-soft: rgba(14, 109, 110, 0.12);
            --warm: #d1833d;
            --line: rgba(23, 50, 77, 0.12);
            --shadow: 0 20px 60px rgba(23, 50, 77, 0.08);
          }

          .stApp {
            background:
              radial-gradient(circle at top left, rgba(14, 109, 110, 0.15), transparent 30%),
              radial-gradient(circle at top right, rgba(209, 131, 61, 0.18), transparent 28%),
              linear-gradient(180deg, #faf6ee 0%, var(--bg) 100%);
            color: var(--ink);
          }

          .block-container {
            padding-top: 2.2rem;
            padding-bottom: 2rem;
          }

          button[role="tab"] {
            font-family: 'Manrope', sans-serif;
            font-weight: 800;
            color: var(--ink);
          }

          h1, h2, h3 {
            font-family: 'Newsreader', serif;
            color: var(--ink);
            letter-spacing: -0.02em;
          }

          p, li, div[data-testid="stMarkdownContainer"] {
            font-family: 'Manrope', sans-serif;
          }

          section[data-testid="stSidebar"] {
            background: rgba(252, 248, 242, 0.86);
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
              linear-gradient(135deg, rgba(14, 109, 110, 0.08), rgba(209, 131, 61, 0.12)),
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
            background: rgba(255, 255, 255, 0.72);
            border: 1px solid rgba(23, 50, 77, 0.08);
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


def _prom_query(expr: str) -> float | None:
    """Run an instant PromQL query and return the scalar value, or *None*."""
    url = f"{_PROMETHEUS_BASE_URL}/api/v1/query?query={urlquote(expr)}"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:  # noqa: S310
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
    refresh: str = "30s",
    variables: dict[str, str] | None = None,
) -> str:
    """Build a Grafana solo-panel embed URL (no chrome, no branding).

    *variables* passes Grafana template variables, e.g.
    ``{"var-spot": "silvaplana", "var-dataset": "data"}``.
    """
    params: dict[str, str | int] = {
        "orgId": 1,
        "theme": "dark",
        "panelId": panel_id,
        "from": from_range,
        "to": "now",
        "refresh": refresh,
        "hideLogo": "true",
    }
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

    # --- Model Status (compact header) -----------------------------------
    model_ver = _prom_query("foehncast_training_pipeline_registered_model_version")
    eval_ok = _prom_query("foehncast_training_pipeline_evaluation_report_exists")
    reg_ok = _prom_query("foehncast_training_pipeline_model_registered")
    verified = (eval_ok is not None and eval_ok >= 1) and (
        reg_ok is not None and reg_ok >= 1
    )
    ver_label = f"v{int(model_ver)}" if model_ver is not None else "—"
    st.metric("Model", f"{ver_label} · {'Verified ✓' if verified else 'Unverified ✗'}")

    # --- Model Confidence (Grafana gauge embed) ---------------------------
    if _grafana_embedding_enabled():
        url = _grafana_solo_panel_url(
            "foehncast-rider",
            "foehncast-rider",
            panel_id=304,
            from_range="now-1h",
        )
        st.iframe(url, height=120)

    st.divider()

    # --- Pipeline Status (side-by-side stats) -----------------------------
    if _grafana_embedding_enabled():
        col_a, col_b = st.columns(2)
        with col_a:
            url = _grafana_solo_panel_url(
                "foehncast-operations",
                "foehncast-operations",
                panel_id=7,
                from_range="now-1h",
            )
            st.iframe(url, height=90)
        with col_b:
            url = _grafana_solo_panel_url(
                "foehncast-operations",
                "foehncast-operations",
                panel_id=8,
                from_range="now-1h",
            )
            st.iframe(url, height=90)

    # --- Stage Timing (bargauge) ------------------------------------------
    if _grafana_embedding_enabled():
        url = _grafana_solo_panel_url(
            "foehncast-operations",
            "foehncast-operations",
            panel_id=22,
            from_range="now-1h",
        )
        st.iframe(url, height=140)

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


def _render_rider_console(
    dashboard_data: dict[str, Any],
    selected_spot_ids: list[str],
    spot_lookup: dict[str, dict[str, Any]],
) -> None:
    ranked_spots = dashboard_data["ranked_spots"]
    prediction_by_spot_id = {
        prediction["spot_id"]: prediction
        for prediction in dashboard_data["predictions"]
    }

    metric_columns = st.columns(4)
    top_spot = ranked_spots[0] if ranked_spots else None
    metric_columns[0].metric("Model version", dashboard_data["model_version"])
    metric_columns[1].metric("Spots in scope", len(selected_spot_ids))
    metric_columns[2].metric("Forecast window", f"{dashboard_data['horizon_hours']} h")
    metric_columns[3].metric(
        "Top signal",
        top_spot["quality_label"] if top_spot is not None else "Unavailable",
    )
    st.caption(horizon_caption(dashboard_data["horizon_hours"]))

    if top_spot is not None:
        st.markdown(
            _top_pick_card(top_spot, dashboard_data["model_version"]),
            unsafe_allow_html=True,
        )

    left_column, right_column = st.columns([1.25, 1.0], gap="large")

    with left_column:
        st.subheader("Ranked Recommendations")
        st.dataframe(
            build_ranking_frame(ranked_spots),
            use_container_width=True,
            hide_index=True,
        )
        st.caption(
            "Ranking combines peak forecast quality, rideable duration, and ride-to-drive return."
        )

    with right_column:
        st.subheader("Forecast Detail")
        focus_spot_ids = [spot["spot_id"] for spot in ranked_spots]
        focus_default = focus_spot_ids[0] if focus_spot_ids else selected_spot_ids[0]
        focus_spot_id = st.selectbox(
            "Spot detail",
            options=focus_spot_ids or selected_spot_ids,
            index=(focus_spot_ids or selected_spot_ids).index(focus_default),
            format_func=lambda spot_id: _spot_label(spot_lookup, spot_id),
        )
        focus_prediction = prediction_by_spot_id[focus_spot_id]
        focus_summary = next(
            spot for spot in ranked_spots if spot["spot_id"] == focus_spot_id
        )
        focus_frame = build_forecast_frame(focus_prediction)

        detail_metrics = st.columns(2)
        detail_metrics[0].metric("Best window", focus_summary["peak_time_label"])
        detail_metrics[1].metric("Rideable hours", focus_summary["rideable_hours"])

        if focus_frame.empty:
            st.info("The current API call returned no forecast rows for this spot.")
        else:
            chart_frame = focus_frame.set_index("time")[["quality_index"]].copy()
            chart_frame["rideable_threshold"] = 2.0
            st.line_chart(chart_frame, use_container_width=True, height=320)

            best_windows = (
                focus_frame.sort_values(
                    ["quality_index", "time"], ascending=[False, True]
                )
                .head(5)
                .loc[:, ["display_time", "quality_index", "quality_label"]]
                .rename(
                    columns={
                        "display_time": "Time",
                        "quality_index": "Quality",
                        "quality_label": "Signal",
                    }
                )
            )
            st.dataframe(best_windows, use_container_width=True, hide_index=True)

    with st.expander("Full forecast rows", expanded=False):
        full_forecast_frame = focus_frame.rename(
            columns={
                "display_time": "Time",
                "quality_index": "Quality",
                "quality_label": "Signal",
                "rideable": "Rideable",
            }
        )
        st.dataframe(
            full_forecast_frame[["Time", "Quality", "Signal", "Rideable"]],
            use_container_width=True,
            hide_index=True,
        )

    st.divider()
    _render_monitoring_tab(_RIDER_GRAFANA)


def _render_system_tab() -> None:
    """System tab: operations + ML diagnostics dashboards."""
    _render_monitoring_tab(_PIPELINE_GRAFANA)
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
        st.caption(f"Grafana base: {_grafana_base_url()}")
        st.divider()
        _render_sidebar_ml_panels()

    _render_timeline_panels()

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
        _render_monitoring_tab(_RIDER_GRAFANA)

    with system_tab:
        _render_system_tab()


main()
