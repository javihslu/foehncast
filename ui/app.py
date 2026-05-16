"""Streamlit rider console for FoehnCast spot recommendations."""

from __future__ import annotations

from typing import Any

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


def main() -> None:
    _inject_styles()
    st.markdown(
        """
        <section class="hero-shell">
          <p class="eyebrow">FoehnCast</p>
          <h1 class="hero-title">Rider Console</h1>
          <p class="hero-lede">
            One rider profile, six Swiss spots, one served model. Ranked recommendations
            combine live Open-Meteo forecasts, engineered wind features, drive-time estimates,
            and the current champion model through the same inference path the API serves.
          </p>
        </section>
        """,
        unsafe_allow_html=True,
    )

    available_spots = _available_spots()
    spot_lookup = {spot["id"]: spot for spot in available_spots}
    default_spot_ids = [spot["id"] for spot in available_spots]

    with st.sidebar:
        st.markdown("### Spot Selection")
        selected_spot_ids = st.multiselect(
            "Spots",
            options=default_spot_ids,
            default=default_spot_ids,
            format_func=lambda spot_id: _spot_label(spot_lookup, spot_id),
            help="Choose the configured spots to include in the live ranking.",
        )
        if st.button("Refresh forecast", use_container_width=True):
            _live_dashboard_data.clear()

    if not selected_spot_ids:
        st.warning("Choose at least one spot to load the live ranking view.")
        st.stop()

    try:
        with st.spinner(
            "Loading forecasts, drive times, and ranked recommendations..."
        ):
            dashboard_data = _live_dashboard_data(tuple(selected_spot_ids))
    except Exception as exc:
        st.error(
            "Could not load the current forecast and model stack. "
            "Check MLflow, network access, and the configured serving model alias."
        )
        st.exception(exc)
        st.stop()

    rider_profile = dashboard_data["rider_profile"]
    ranked_spots = dashboard_data["ranked_spots"]
    prediction_by_spot_id = {
        prediction["spot_id"]: prediction
        for prediction in dashboard_data["predictions"]
    }

    with st.sidebar:
        st.markdown(_profile_card(rider_profile), unsafe_allow_html=True)
        st.caption(
            "Drive-time ranking uses the rider home from config.yaml and live OSRM route estimates."
        )

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


main()
