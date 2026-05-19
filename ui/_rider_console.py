"""Rider console: quality timeline, wind chart, spot switcher, ranked grid."""

from __future__ import annotations

import json
import math
from typing import Any

import altair as alt
import pandas as pd
import streamlit as st

from foehncast.config import get_rider_config, get_spots
from foehncast.feature_pipeline.ingest import fetch_forecast

from ui._sidebar import render_spot_map


def spot_label(spot_lookup: dict[str, dict[str, Any]], spot_id: str) -> str:
    spot = spot_lookup[spot_id]
    return f"{spot['name']} ({spot_id})"


def profile_card(rider_profile: dict[str, Any]) -> str:
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


def top_pick_card(top_spot: dict[str, Any], model_version: str) -> str:
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


@st.cache_data(ttl=1800, show_spinner=False)
def focus_spot_timeline(spot_id: str, *, past_days: int = 1) -> pd.DataFrame:
    """Return wind speed at three elevations for a single spot."""
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


@st.cache_data(ttl=1800, show_spinner=False)
def spot_quality_timeline(spot_id: str, predictions_json: str) -> pd.DataFrame:
    """Build a quality-index timeline combining past predictions, actuals, and forecast."""
    from foehncast.monitoring.prediction_log import read_prediction_history
    from foehncast.feature_pipeline.engineer import engineer_features
    from foehncast.feature_pipeline.ingest import fetch_archive
    from foehncast.training_pipeline.label import compute_quality_index

    predictions: list[dict[str, Any]] = json.loads(predictions_json)

    frames: list[pd.DataFrame] = []
    now = pd.Timestamp.now(tz="UTC")

    # 1. Past predictions from the durable prediction log.
    try:
        history = read_prediction_history(retention_days=3)
        if not history.empty:
            spot_history = history[history["spot_id"] == spot_id].copy()
            if not spot_history.empty:
                spot_history["forecast_time"] = pd.to_datetime(
                    spot_history["forecast_time"], utc=True
                )
                past_preds = spot_history[spot_history["forecast_time"] < now]
                if not past_preds.empty:
                    past_pred_frame = pd.DataFrame(
                        {
                            "time": past_preds["forecast_time"],
                            "quality_index": past_preds["quality_index"].astype(float),
                            "series": "Predicted (past)",
                        }
                    )
                    frames.append(past_pred_frame)
    except Exception:
        pass

    # 2. Observed actuals.
    try:
        spot = next((s for s in get_spots() if s["id"] == spot_id), None)
        if spot is not None:
            end_date = (now - pd.Timedelta(hours=6)).strftime("%Y-%m-%d")
            start_date = (now - pd.Timedelta(days=3)).strftime("%Y-%m-%d")
            raw = fetch_archive(spot["lat"], spot["lon"], start_date, end_date)
            if not raw.empty:
                rider_config = get_rider_config()
                engineered = engineer_features(raw, spot["shore_orientation_deg"])
                quality = compute_quality_index(engineered, rider_config)
                idx = engineered.index
                if idx.tz is None:
                    idx = idx.tz_localize("UTC")
                else:
                    idx = idx.tz_convert("UTC")
                obs_frame = pd.DataFrame(
                    {
                        "time": idx,
                        "quality_index": quality.values.astype(float),
                        "series": "Observed",
                    }
                )
                frames.append(obs_frame)
    except Exception:
        pass

    # 3. Future predictions from the current inference run.
    spot_pred = next((p for p in predictions if p["spot_id"] == spot_id), None)
    if spot_pred and spot_pred.get("forecast"):
        forecast_rows = spot_pred["forecast"]
        forecast_frame = pd.DataFrame(
            {
                "time": pd.to_datetime([r["time"] for r in forecast_rows], utc=True),
                "quality_index": [float(r["quality_index"]) for r in forecast_rows],
                "series": "Forecast",
            }
        )
        frames.append(forecast_frame)

    if not frames:
        return pd.DataFrame(columns=["time", "quality_index", "series"])

    combined = pd.concat(frames, ignore_index=True)
    combined["time"] = pd.to_datetime(combined["time"], utc=True)
    return combined.sort_values("time")


@st.fragment
def render_rider_console(
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
        # --- Quality index timeline ---
        predictions_list = dashboard_data.get("predictions", [])
        quality_frame = spot_quality_timeline(
            focus_spot_id, json.dumps(predictions_list, default=str)
        )
        if not quality_frame.empty:
            st.subheader(f"Ride quality — {spot_label(spot_lookup, focus_spot_id)}")
            q_tz = quality_frame["time"].dt.tz
            q_now = (
                pd.Timestamp.now(tz=q_tz)
                if q_tz is not None
                else pd.Timestamp.now(tz="UTC")
            )
            series_colors = {
                "Predicted (past)": "#3b5a5a",
                "Observed": "#0e8a86",
                "Forecast": "#ff7a26",
            }
            series_present = [
                s
                for s in ["Predicted (past)", "Observed", "Forecast"]
                if s in quality_frame["series"].unique()
            ]
            q_lines = (
                alt.Chart(quality_frame)
                .mark_line(interpolate="monotone", strokeWidth=2.2, point=True)
                .encode(
                    x=alt.X("time:T", title="Time"),
                    y=alt.Y(
                        "quality_index:Q",
                        title="Quality index",
                        scale=alt.Scale(domain=[0, 5]),
                    ),
                    color=alt.Color(
                        "series:N",
                        scale=alt.Scale(
                            domain=series_present,
                            range=[series_colors[s] for s in series_present],
                        ),
                        legend=alt.Legend(title="Series", orient="top"),
                    ),
                    strokeDash=alt.StrokeDash(
                        "series:N",
                        scale=alt.Scale(
                            domain=series_present,
                            range=[
                                [4, 4] if s == "Predicted (past)" else [1, 0]
                                for s in series_present
                            ],
                        ),
                        legend=None,
                    ),
                )
            )
            q_now_rule = (
                alt.Chart(pd.DataFrame({"x": [q_now]}))
                .mark_rule(color="#ff7a26", strokeWidth=2)
                .encode(x="x:T")
            )
            q_threshold = (
                alt.Chart(pd.DataFrame({"y": [3.0]}))
                .mark_rule(color="#0e8a86", strokeDash=[4, 4], strokeWidth=1.2)
                .encode(y="y:Q")
            )
            q_threshold_label = (
                alt.Chart(pd.DataFrame({"y": [3.0], "label": ["Rideable"]}))
                .mark_text(
                    align="left",
                    baseline="bottom",
                    dx=6,
                    dy=-3,
                    color="#0e8a86",
                    fontSize=10,
                )
                .encode(y="y:Q", text="label:N")
            )
            st.altair_chart(
                (q_lines + q_threshold + q_threshold_label + q_now_rule)
                .properties(height=220, background="transparent")
                .configure_view(strokeWidth=0, fill=None)
                .configure_axis(
                    domainColor="#3b5a5a",
                    gridColor="rgba(7, 37, 42, 0.10)",
                    labelColor="#07252a",
                    titleColor="#07252a",
                ),
                use_container_width=True,
            )

        # --- Wind speed timeline ---
        timeline_frame = focus_spot_timeline(focus_spot_id)
        with st.expander(
            f"Wind speed — {spot_label(spot_lookup, focus_spot_id)}", expanded=False
        ):
            if timeline_frame.empty:
                st.info("No timeline data available for this spot right now.")
            else:
                tz = timeline_frame["time"].dt.tz
                now_ts = (
                    pd.Timestamp.now(tz=tz) if tz is not None else pd.Timestamp.now()
                )
                kn_to_kmh = 1.852
                threshold_kmh = 12.0 * kn_to_kmh
                elevation_order = ["10m", "80m", "120m"]
                elevations_present = [
                    e
                    for e in elevation_order
                    if e in timeline_frame["elevation"].unique()
                ]

                past_min = timeline_frame["time"].min()
                past_band = pd.DataFrame({"x": [past_min], "x2": [now_ts]})
                past_rect = (
                    alt.Chart(past_band)
                    .mark_rect(color="#07252a", opacity=0.07)
                    .encode(x="x:T", x2="x2:T")
                )

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
                                    2
                                    * math.pi
                                    * ((ts.hour + ts.minute / 60.0) - 12)
                                    / 24.0
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

        # Spot switcher buttons
        n = len(focus_spot_ids)
        if n:
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
                    st.rerun(scope="fragment")

            # Transposed metrics grid
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

    render_spot_map(ranked_spots)
