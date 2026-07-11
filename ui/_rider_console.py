"""Rider console: quality timeline, wind chart, spot switcher, ranked grid."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import altair as alt
import pandas as pd
import streamlit as st

from foehncast.config import (
    get_api_config,
    get_labeling_config,
    get_rider_config,
    get_spots,
)
from foehncast.feature_pipeline.ingest import fetch_forecast
from foehncast.inference_pipeline.dashboard import (
    _RIDEABLE_QUALITY_THRESHOLD,
    quality_bucket,
)
from foehncast.solar import is_daylight, night_intervals, solar_elevation_deg

from _wind_map import render_wind_map


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


def _minimum_rideable_kts() -> float:
    """Minimum rideable 10 m wind for the configured rider, in knots.

    Mirrors the labeling threshold so the chart's rideable line matches the
    quality model's own cut-off instead of a hardcoded value.
    """
    cfg = get_labeling_config()["minimum_wind_speed_10m"]
    rider = get_rider_config()
    if rider["weight_kg"] <= cfg["light_rider_max_weight_kg"]:
        return float(cfg["light_rider_min_kts"])
    return float(cfg["default_min_kts"])


# Day-granularity time axis: one tick per day, weekday + day-of-month labels.
_DAY_AXIS = alt.Axis(
    format="%a %d",
    tickCount={"interval": "day", "step": 1},
    labelAngle=0,
    grid=False,
)


# One-hue ramp for the ordered elevation series; gusts differ by dash too.
_ELEVATION_COLORS = {
    "10m": "#5fa7a1",
    "80m": "#20837c",
    "120m": "#0b5e60",
    "gusts": "#3b5a5a",
}

# Ordinal 5-step teal ramp for the all-spots session-quality heatmap, light
# (quality 1) to dark (quality 5), anchored on the rideable teal (_dial_tokens
# RIDEABLE #0aa392). Validated in --ordinal mode against the actual page
# surface #eaf3ef: single hue, monotone lightness, visible step gaps, and a
# light end that clears 2:1 so even a "1" cell reads as a mark.
_QUALITY_RAMP = ["#45b0a2", "#1d9c8e", "#0f8478", "#0a6459", "#0a4a42"]

# Hairline between heatmap cells in the page surface tone so neighbouring hours
# never fuse into a stripe (the gap separates, not a data-coloured border).
_HEATMAP_GAP = "#eaf3ef"

# Row height per spot; the grid grows with the spot count and the container
# takes the x-axis band, so the axis labels never get clipped.
_HEATMAP_ROW_PX = 30


def _night_bands(
    t_min: pd.Timestamp, t_max: pd.Timestamp, lat: float, lon: float
) -> pd.DataFrame:
    """Dusk-to-dawn rectangles for the spot, from real solar geometry."""
    intervals = night_intervals(lat, lon, t_min, t_max)
    return pd.DataFrame([{"x": lo, "x2": hi} for lo, hi in intervals])


def _night_rect(
    t_min: pd.Timestamp, t_max: pd.Timestamp, lat: float, lon: float
) -> alt.Chart:
    """Altair layer obscuring night hours with a dark wash."""
    return (
        alt.Chart(_night_bands(t_min, t_max, lat, lon))
        .mark_rect(color="#07252a", opacity=0.28)
        .encode(x="x:T", x2="x2:T")
    )


@st.cache_data(ttl=1800, show_spinner=False)
def focus_spot_timeline(spot_id: str, *, past_days: int = 1) -> pd.DataFrame:
    """Return wind speed (10/80/120 m) and 10 m gusts for a single spot."""
    spot = next((s for s in get_spots() if s["id"] == spot_id), None)
    if spot is None:
        return pd.DataFrame(columns=["time", "elevation", "wind_speed"])

    forecast_df = fetch_forecast(spot["lat"], spot["lon"], past_days=past_days)
    if forecast_df.empty:
        return pd.DataFrame(columns=["time", "elevation", "wind_speed"])

    wide = forecast_df.reset_index().rename(columns={"index": "time"})
    keep = [
        c
        for c in (
            "wind_speed_10m",
            "wind_speed_80m",
            "wind_speed_120m",
            "wind_gusts_10m",
        )
        if c in wide.columns
    ]
    if not keep:
        return pd.DataFrame(columns=["time", "elevation", "wind_speed"])
    long = wide[["time", *keep]].melt(
        id_vars="time", var_name="elevation", value_name="wind_speed"
    )
    long["elevation"] = (
        long["elevation"]
        .str.replace("wind_gusts_10m", "gusts")
        .str.replace("wind_speed_", "")
    )
    long["time"] = pd.to_datetime(long["time"])
    return long


@st.cache_data(ttl=1800, show_spinner=False)
def _prediction_history_cached() -> pd.DataFrame:
    """Read prediction history once and cache for all spots."""
    from foehncast.monitoring.prediction_log import read_prediction_history

    try:
        return read_prediction_history(retention_days=3)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=1800, show_spinner=False)
def spot_quality_timeline(spot_id: str, predictions_json: str) -> pd.DataFrame:
    """Build a quality-index timeline combining past predictions, actuals, and forecast."""
    from foehncast.feature_pipeline.engineer import engineer_features
    from foehncast.feature_pipeline.ingest import fetch_archive
    from foehncast.training_pipeline.label import compute_quality_index

    predictions: list[dict[str, Any]] = json.loads(predictions_json)

    frames: list[pd.DataFrame] = []
    now = pd.Timestamp.now(tz="UTC")

    # 1. Past predictions from the durable prediction log (shared cache).
    history = _prediction_history_cached()
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


def prewarm_spot_caches(spot_ids: list[str], predictions_json: str) -> None:
    """Pre-warm timeline caches for all spots in parallel.

    Calls focus_spot_timeline and spot_quality_timeline for each spot
    concurrently so that switching spots via buttons is instant.
    """
    # Warm the shared prediction history cache first (single BigQuery read)
    # before spawning per-spot threads.
    _prediction_history_cached()

    def _warm(spot_id: str) -> None:
        focus_spot_timeline(spot_id)
        spot_quality_timeline(spot_id, predictions_json)

    with ThreadPoolExecutor(max_workers=min(len(spot_ids), 6)) as pool:
        futures = [pool.submit(_warm, sid) for sid in spot_ids]
        for f in as_completed(futures):
            try:
                f.result()
            except Exception:
                pass


@st.cache_data(ttl=1800, show_spinner=False)
def all_spots_quality_grid(
    spot_ids: tuple[str, ...], predictions_json: str, display_tz: str
) -> pd.DataFrame:
    """Hourly quality band (1-5) per spot over the forecast window.

    Quality reuses the ranked predictions already in dashboard_data (the /rank
    flow computed them), so nothing re-runs inference. Wind and gusts come from
    the already-warmed focus_spot_timeline cache for the tooltip only — a cache
    hit, never a new fetch. Each row is one cell: spot x hour.
    """
    predictions = json.loads(predictions_json)
    pred_by_spot = {p["spot_id"]: p for p in predictions}

    frames: list[pd.DataFrame] = []
    for spot_id in spot_ids:
        prediction = pred_by_spot.get(spot_id)
        forecast_rows = prediction.get("forecast", []) if prediction else []
        if not forecast_rows:
            continue
        frame = pd.DataFrame(
            {
                "time": pd.to_datetime([r["time"] for r in forecast_rows], utc=True),
                "quality": [
                    max(1, quality_bucket(r["quality_index"])) for r in forecast_rows
                ],
            }
        )
        frame["spot_id"] = spot_id

        # Merge 10 m wind and gusts from the warmed focus timeline (long form),
        # joined on the UTC hour so tz differences never misalign. Missing wind
        # just leaves the tooltip fields blank; the quality cell still renders.
        wind = focus_spot_timeline(spot_id)
        picked = (
            wind[wind["elevation"].isin(["10m", "gusts"])].copy()
            if not wind.empty
            else wind
        )
        if not picked.empty:
            picked["hour"] = pd.to_datetime(picked["time"], utc=True).dt.floor("h")
            wide = (
                picked.pivot_table(
                    index="hour", columns="elevation", values="wind_speed"
                )
                .reindex(columns=["10m", "gusts"])
                .rename(columns={"10m": "wind", "gusts": "gust"})
            )
            frame["hour"] = frame["time"].dt.floor("h")
            frame = frame.merge(wide, left_on="hour", right_index=True, how="left")
            frame = frame.drop(columns="hour")
        frames.append(frame)

    if not frames:
        return pd.DataFrame(columns=["time", "quality", "spot_id"])

    grid = pd.concat(frames, ignore_index=True)
    grid["time"] = grid["time"].dt.tz_convert(display_tz)
    grid["time_end"] = grid["time"] + pd.Timedelta(hours=1)
    return grid


@st.fragment
def render_rider_console(
    dashboard_data: dict[str, Any],
    selected_spot_ids: list[str],
    spot_lookup: dict[str, dict[str, Any]],
) -> None:
    ranked_spots = dashboard_data["ranked_spots"]

    # Focus timeline (full width, past + future)
    focus_spot_ids = [spot["spot_id"] for spot in ranked_spots] or selected_spot_ids
    default_focus = focus_spot_ids[0] if focus_spot_ids else None
    if "rider_focus_spot" not in st.session_state or (
        st.session_state["rider_focus_spot"] not in focus_spot_ids
    ):
        st.session_state["rider_focus_spot"] = default_focus

    focus_spot_id = st.session_state.get("rider_focus_spot") or default_focus

    if focus_spot_id is not None:
        spot_cfg = next(s for s in get_spots() if s["id"] == focus_spot_id)
        spot_lat, spot_lon = float(spot_cfg["lat"]), float(spot_cfg["lon"])
        display_tz = get_api_config()["open_meteo"]["timezone"]

        # Quality index timeline
        predictions_list = dashboard_data.get("predictions", [])
        quality_frame = spot_quality_timeline(
            focus_spot_id, json.dumps(predictions_list, default=str)
        )
        if not quality_frame.empty:
            quality_frame["time"] = quality_frame["time"].dt.tz_convert(display_tz)
            quality_frame["is_day"] = is_daylight(
                spot_lat, spot_lon, pd.DatetimeIndex(quality_frame["time"])
            ).to_numpy()
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

            def q_layer(data: pd.DataFrame, dim: bool) -> alt.Chart:
                return (
                    alt.Chart(data)
                    .mark_line(
                        interpolate="monotone",
                        strokeWidth=1.6 if dim else 2.2,
                        point=not dim,
                        opacity=0.3 if dim else 1.0,
                    )
                    .encode(
                        x=alt.X("time:T", title="Day", axis=_DAY_AXIS),
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
                            # Same legend on both layers: the shared color scale
                            # renders it once; None here would suppress it entirely.
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

            # Night hours render dimmed underneath; daylight at full strength.
            q_lines = q_layer(quality_frame, dim=True) + q_layer(
                quality_frame[quality_frame["is_day"]], dim=False
            )
            q_now_rule = (
                alt.Chart(pd.DataFrame({"x": [q_now]}))
                .mark_rule(color="#ff7a26", strokeWidth=2)
                .encode(x="x:T")
            )
            q_threshold = (
                alt.Chart(pd.DataFrame({"y": [_RIDEABLE_QUALITY_THRESHOLD]}))
                .mark_rule(color="#0e8a86", strokeDash=[4, 4], strokeWidth=1.2)
                .encode(y="y:Q")
            )
            q_threshold_label = (
                alt.Chart(
                    pd.DataFrame(
                        {"y": [_RIDEABLE_QUALITY_THRESHOLD], "label": ["Rideable"]}
                    )
                )
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
            q_night = _night_rect(
                quality_frame["time"].min(),
                quality_frame["time"].max(),
                spot_lat,
                spot_lon,
            )
            st.altair_chart(
                (q_night + q_lines + q_threshold + q_threshold_label + q_now_rule)
                .properties(height=180, background="transparent")
                .configure_view(strokeWidth=0, fill=None)
                .configure_axis(
                    domainColor="#3b5a5a",
                    gridColor="rgba(7, 37, 42, 0.10)",
                    labelColor="#07252a",
                    titleColor="#07252a",
                )
                .configure_legend(
                    labelColor="#07252a",
                    titleColor="#07252a",
                    labelFont="Manrope",
                    titleFont="Manrope",
                    labelFontSize=13,
                    titleFontSize=12,
                    labelFontWeight=600,
                    titleFontWeight=700,
                    symbolSize=140,
                    symbolStrokeWidth=3,
                ),
                use_container_width=True,
                theme=None,
            )

        # Wind and gust timeline (the features the model reads)
        st.subheader(f"Wind & gusts — {spot_label(spot_lookup, focus_spot_id)}")
        timeline_frame = focus_spot_timeline(focus_spot_id)
        if timeline_frame.empty:
            st.info("No timeline data available for this spot right now.")
        else:
            tz = timeline_frame["time"].dt.tz
            now_ts = pd.Timestamp.now(tz=tz) if tz is not None else pd.Timestamp.now()
            kn_to_kmh = 1.852
            min_kts = _minimum_rideable_kts()
            threshold_kmh = min_kts * kn_to_kmh
            elevation_order = ["10m", "80m", "120m", "gusts"]
            elevations_present = [
                e for e in elevation_order if e in timeline_frame["elevation"].unique()
            ]
            timeline_frame["is_day"] = is_daylight(
                spot_lat, spot_lon, pd.DatetimeIndex(timeline_frame["time"])
            ).to_numpy()

            night_rect = _night_rect(
                timeline_frame["time"].min(),
                timeline_frame["time"].max(),
                spot_lat,
                spot_lon,
            )

            def wind_layer(data: pd.DataFrame, dim: bool) -> alt.Chart:
                return (
                    alt.Chart(data)
                    .mark_line(
                        interpolate="monotone",
                        strokeWidth=1.6 if dim else 2.2,
                        opacity=0.3 if dim else 1.0,
                    )
                    .encode(
                        x=alt.X("time:T", title="Day", axis=_DAY_AXIS),
                        y=alt.Y(
                            "wind_speed:Q",
                            title="Wind speed (km/h)",
                        ),
                        color=alt.Color(
                            "elevation:N",
                            scale=alt.Scale(
                                domain=elevations_present,
                                range=[
                                    _ELEVATION_COLORS[e] for e in elevations_present
                                ],
                            ),
                            legend=alt.Legend(title="Elevation", orient="top"),
                        ),
                        strokeDash=alt.StrokeDash(
                            "elevation:N",
                            scale=alt.Scale(
                                domain=elevations_present,
                                range=[
                                    [5, 4] if e == "gusts" else [1, 0]
                                    for e in elevations_present
                                ],
                            ),
                            legend=None,
                        ),
                    )
                )

            # Night hours render dimmed underneath; daylight at full strength.
            lines = wind_layer(timeline_frame, dim=True) + wind_layer(
                timeline_frame[timeline_frame["is_day"]], dim=False
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
                            "label": [f"{int(min_kts)} kn rideable"],
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
            )
            now_rule = (
                alt.Chart(pd.DataFrame({"x": [now_ts]}))
                .mark_rule(color="#ff7a26", strokeWidth=2)
                .encode(x="x:T")
            )
            # Solar-elevation curve along the chart bottom, pre-scaled into
            # wind-speed units so it shares the axis without a second scale.
            strip_times = pd.date_range(
                timeline_frame["time"].min().floor("h"),
                timeline_frame["time"].max().ceil("h"),
                freq="30min",
            )
            elevation = solar_elevation_deg(spot_lat, spot_lon, strip_times).clip(
                lower=0.0
            )
            peak = float(elevation.max()) or 1.0
            band_kmh = 0.12 * max(
                float(timeline_frame["wind_speed"].max()), threshold_kmh
            )
            solar_frame = pd.DataFrame(
                {
                    "time": strip_times,
                    "solar": elevation.to_numpy() / peak * band_kmh,
                }
            )
            solar_area = (
                alt.Chart(solar_frame)
                .mark_area(
                    color="#1f5e44",
                    opacity=0.22,
                    line={"color": "#1f5e44", "strokeWidth": 1.0},
                )
                .encode(x="time:T", y="solar:Q")
            )
            st.altair_chart(
                (
                    night_rect
                    + solar_area
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
                )
                .configure_legend(
                    labelColor="#07252a",
                    titleColor="#07252a",
                    labelFont="Manrope",
                    titleFont="Manrope",
                    labelFontSize=13,
                    titleFontSize=12,
                    labelFontWeight=600,
                    titleFontWeight=700,
                    symbolSize=140,
                    symbolStrokeWidth=3,
                ),
                use_container_width=True,
                theme=None,
            )
            st.caption(
                "Green band along the chart bottom traces solar elevation "
                "(daylight strength), scaled to the wind-speed axis."
            )

        # All-spots session-quality heatmap: every ranked spot on one grid so
        # they compare at a glance, best spot on the top row. No night shading
        # here - daylight is already baked into the score.
        heat_grid = all_spots_quality_grid(
            tuple(spot["spot_id"] for spot in ranked_spots),
            json.dumps(predictions_list, default=str),
            display_tz,
        )
        if not heat_grid.empty:
            heat_grid = heat_grid.assign(
                spot=heat_grid["spot_id"].map(lambda sid: spot_lookup[sid]["name"])
            )
            rank_order = [
                spot_lookup[s["spot_id"]]["name"]
                for s in ranked_spots
                if s["spot_id"] in spot_lookup
            ]
            tooltip = [
                alt.Tooltip("spot:N", title="Spot"),
                alt.Tooltip("time:T", title="Time", format="%a %d %H:%M"),
                alt.Tooltip("quality:O", title="Quality (1-5)"),
            ]
            if "wind" in heat_grid.columns:
                tooltip.append(alt.Tooltip("wind:Q", title="Wind (km/h)", format=".0f"))
            if "gust" in heat_grid.columns:
                tooltip.append(
                    alt.Tooltip("gust:Q", title="Gusts (km/h)", format=".0f")
                )

            st.subheader("All spots — session quality")
            heatmap = (
                alt.Chart(heat_grid)
                .mark_rect(stroke=_HEATMAP_GAP, strokeWidth=1)
                .encode(
                    x=alt.X(
                        "time:T",
                        title="Day",
                        axis=_DAY_AXIS,
                        scale=alt.Scale(nice=False),
                    ),
                    x2="time_end:T",
                    y=alt.Y("spot:N", title=None, sort=rank_order),
                    color=alt.Color(
                        "quality:O",
                        scale=alt.Scale(domain=[1, 2, 3, 4, 5], range=_QUALITY_RAMP),
                        legend=alt.Legend(
                            title="Session quality (1-5)",
                            orient="top",
                            direction="horizontal",
                            symbolType="square",
                        ),
                    ),
                    tooltip=tooltip,
                )
                .properties(
                    height=_HEATMAP_ROW_PX * max(len(rank_order), 1),
                    background="transparent",
                )
                .configure_view(strokeWidth=0, fill=None)
                .configure_axis(
                    domainColor="#3b5a5a",
                    labelColor="#07252a",
                    titleColor="#07252a",
                )
                .configure_legend(
                    labelColor="#07252a",
                    titleColor="#07252a",
                    labelFont="Manrope",
                    titleFont="Manrope",
                    labelFontSize=13,
                    titleFontSize=12,
                    labelFontWeight=600,
                    titleFontWeight=700,
                    symbolSize=200,
                )
            )
            st.altair_chart(heatmap, use_container_width=True, theme=None)

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
                    "Rideable hrs (day)",
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
            # Per-spot detail table, demoted below the heatmap: the grid is the
            # table view, kept for exact values but out of the way by default.
            with st.expander("Spot metrics", expanded=False):
                st.markdown(
                    f'<div class="ranked-stack" style="grid-template-columns:{grid_cols}">'
                    f'<div class="col lead">{lead_cells}</div>'
                    + "".join(spot_cols_html)
                    + "</div>",
                    unsafe_allow_html=True,
                )

    st.divider()

    render_wind_map(ranked_spots, _minimum_rideable_kts())
