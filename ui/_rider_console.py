"""Rider console: quality timeline, wind chart, spot switcher, ranked grid."""

from __future__ import annotations

import base64
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
    quality_label,
)
from foehncast.solar import is_daylight, night_intervals, solar_elevation_deg

from _dial_svg import wind_dial_svg
from _dial_tokens import INK, rgb_to_hex
from _wind_map import (
    _KN_TO_KMH,
    _clamp_to_slider_option,
    _compass,
    _spot_wind_frame,
    render_wind_map,
)


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

# Heatmap x-axis: a tick every 6 h (48 h / 6 h = 9 ticks). Midnight ticks
# render the weekday + day-of-month, the rest just the hour, so the day
# boundary still reads without a second axis row.
_HEATMAP_X_AXIS = alt.Axis(
    tickCount=9,
    labelExpr=(
        "timeFormat(datum.value, '%H') == '00' "
        "? timeFormat(datum.value, '%a %d') "
        ": timeFormat(datum.value, '%H')"
    ),
    labelAngle=0,
    grid=False,
    labelFontSize=13,
    title=None,
)


# One-hue ramp for the ordered elevation series; gusts differ by dash too.
_ELEVATION_COLORS = {
    "10m": "#5fa7a1",
    "80m": "#20837c",
    "120m": "#0b5e60",
    "gusts": "#3b5a5a",
}

# Ordinal 4-step teal ramp for the all-spots session-quality heatmap, covering
# levels 2-5 (light to dark). Level 1 gets no ramp color at all: the dataviz
# validator (--ordinal mode, page surface #eaf3ef) proved a background-
# matching FILL cannot clear the 2:1 light-end floor, so a "1" cell maps to
# "transparent" in the color scale (in-domain, so it still renders its stroke
# and hit-tests). This four-step range passes: monotone lightness, visible
# step gaps, 2.18:1 light end, 2 deg hue spread.
_QUALITY_RAMP = ["#63b3a4", "#2f9384", "#0f7263", "#084c42"]

# Hairline between heatmap cells. Faint ink rather than the page surface tone:
# level-1 cells are fill-free, and a surface-toned stroke would vanish on the
# surface -- this keeps the flat-week "outline board" visible while reading as
# normal gridwork between filled cells.
_HEATMAP_GAP = "rgba(7, 37, 42, 0.16)"

_LEGEND_CHIP = (
    '<span style="display:inline-block;width:0.7rem;height:0.7rem;'
    "border-radius:2px;{swatch};margin:0 0.3rem 0 0.9rem;"
    'vertical-align:-0.05rem"></span>{level}'
)


def _quality_legend_html() -> str:
    """Manual chip row for the heatmap legend, level 1 through 5.

    The Vega legend would render level 1 as a transparent (invisible) swatch,
    since the color scale maps it to "transparent". Built by hand instead,
    mirroring the wind map's chip row (_wind_map.render_wind_map): chip 1 is
    an outline-only swatch, chips 2-5 use the validated ramp.
    """
    swatches = ["border:1px solid rgba(7, 37, 42, 0.4)"] + [
        f"background:{color}" for color in _QUALITY_RAMP
    ]
    chips = "".join(
        _LEGEND_CHIP.format(swatch=swatch, level=level)
        for level, swatch in zip((1, 2, 3, 4, 5), swatches, strict=True)
    )
    return (
        "<p style=\"color:#07252a;font-family:'Manrope',sans-serif;"
        'font-size:0.8rem;font-weight:600;margin:0 0 0.4rem 0">'
        f"Session quality (1-5){chips}</p>"
    )


# Row height per spot; the grid grows with the spot count and the container
# takes the x-axis band, so the axis labels never get clipped.
_HEATMAP_ROW_PX = 30

# Compact wind dial embedded per heatmap cell as a base64 data URI; small since
# it renders inside a hover bubble. Spot-level metric columns the tooltip pulls
# from ranked_spots, constant per spot but carried on every cell row.
_TOOLTIP_DIAL_PX = 120
_SPOT_METRIC_KEYS = (
    "quality_label",
    "quality_index",
    "rideable_hours",
    "drive_minutes",
    "session_hours",
    "ride_drive_ratio",
    "score",
)


def _night_bands(
    t_min: pd.Timestamp, t_max: pd.Timestamp, lat: float, lon: float
) -> pd.DataFrame:
    """Dusk-to-dawn rectangles for the spot, from real solar geometry."""
    intervals = night_intervals(lat, lon, t_min, t_max)
    return pd.DataFrame([{"x": lo, "x2": hi} for lo, hi in intervals])


def _night_rect(
    t_min: pd.Timestamp,
    t_max: pd.Timestamp,
    lat: float,
    lon: float,
    x_scale: Any = alt.Undefined,
) -> alt.Chart:
    """Altair layer obscuring night hours with a dark wash.

    Clipped and sharing the caller's pinned x scale so a night band reaching
    past the shared domain neither draws outside the plot nor stretches it.
    """
    return (
        alt.Chart(_night_bands(t_min, t_max, lat, lon))
        .mark_rect(color="#07252a", opacity=0.28, clip=True)
        .encode(x=alt.X("x:T", scale=x_scale), x2="x2:T")
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


def _compact_dial_uri(
    direction: float | None,
    wind_kmh: float | None,
    gust_kmh: float | None,
    shore_deg: float,
    min_kts: float,
) -> str:
    """Base64 SVG data URI of the compact wind dial for one cell, or "".

    Empty when wind or direction is missing so the tooltip just drops the image.
    The base64 alphabet has no raw ``&`` or ``<``, so the URI is tooltip-safe.
    """
    if direction is None or wind_kmh is None or pd.isna(direction) or pd.isna(wind_kmh):
        return ""
    gust = 0.0 if gust_kmh is None or pd.isna(gust_kmh) else float(gust_kmh)
    svg = wind_dial_svg(
        direction_deg=float(direction),
        speed_kn=float(wind_kmh) / _KN_TO_KMH,
        gust_kn=gust / _KN_TO_KMH,
        shore_orientation_deg=shore_deg,
        min_kts=min_kts,
        size_px=_TOOLTIP_DIAL_PX,
        detail="compact",
    )
    b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"


@st.cache_data(ttl=1800, show_spinner=False)
def all_spots_quality_grid(
    spot_ids: tuple[str, ...],
    predictions_json: str,
    display_tz: str,
    ranked_json: str,
) -> pd.DataFrame:
    """Hourly quality band (1-5) per spot over the forecast window, with tooltip payload.

    Quality reuses the ranked predictions already in dashboard_data (the /rank
    flow computed them), so nothing re-runs inference. Wind and gusts come from
    the warmed focus_spot_timeline cache and direction from the map's
    _spot_wind_frame cache — both cache hits, never new fetches. Each row is one
    cell (spot x hour) carrying the tooltip header, a compact base64 dial, and
    the spot-level ranked metrics, all built once inside this cached frame.
    """
    predictions = json.loads(predictions_json)
    pred_by_spot = {p["spot_id"]: p for p in predictions}
    meta_by_spot = {m["spot_id"]: m for m in json.loads(ranked_json)}
    spots_cfg = {s["id"]: s for s in get_spots()}
    min_kts = _minimum_rideable_kts()

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
        frame["hour"] = frame["time"].dt.floor("h")

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
            frame = frame.merge(wide, left_on="hour", right_index=True, how="left")

        # Direction reuses the map's per-spot frame (the same source the detail
        # panel and map dials read), merged on the UTC hour so the dials agree.
        wind_frame = _spot_wind_frame(spot_id)
        if not wind_frame.empty and "wind_direction_10m" in wind_frame.columns:
            idx = pd.to_datetime(wind_frame.index, utc=True).floor("h")
            by_hour = pd.Series(wind_frame["wind_direction_10m"].to_numpy(), index=idx)
            by_hour = by_hour[~by_hour.index.duplicated()]
            frame["direction"] = frame["hour"].map(by_hour)

        frames.append(frame.drop(columns="hour"))

    if not frames:
        return pd.DataFrame(columns=["time", "quality", "spot_id"])

    grid = pd.concat(frames, ignore_index=True)
    grid["time"] = grid["time"].dt.tz_convert(display_tz)
    grid["time_end"] = grid["time"] + pd.Timedelta(hours=1)
    if "direction" not in grid.columns:
        grid["direction"] = pd.NA

    # Tooltip payload, built once here so the fragment's reruns only serialize.
    # Header is "SpotName - Ddd HH:00" in local time; the dial is a compact
    # base64 SVG; metrics come straight from the ranked cards (constant per spot).
    spot_names = grid["spot_id"].map(
        lambda sid: spots_cfg[sid]["name"] if sid in spots_cfg else sid
    )
    grid["header"] = spot_names + " - " + grid["time"].dt.strftime("%a %H:00")
    shore = grid["spot_id"].map(
        lambda sid: (
            float(spots_cfg[sid]["shore_orientation_deg"]) if sid in spots_cfg else 0.0
        )
    )
    n = len(grid)
    wind_vals = grid["wind"].to_numpy() if "wind" in grid.columns else [None] * n
    gust_vals = grid["gust"].to_numpy() if "gust" in grid.columns else [None] * n
    grid["dial"] = [
        _compact_dial_uri(d, w, g, s, min_kts)
        for d, w, g, s in zip(
            grid["direction"].to_numpy(),
            wind_vals,
            gust_vals,
            shore.to_numpy(),
            strict=True,
        )
    ]
    grid["direction"] = grid["direction"].map(
        lambda d: "" if pd.isna(d) else f"{_compass(float(d))} ({float(d):.0f}°)"
    )
    for key in _SPOT_METRIC_KEYS:
        grid[key] = grid["spot_id"].map(
            lambda sid, k=key: meta_by_spot.get(sid, {}).get(k)
        )
    return grid


def _selected_heat_cell(event: Any, grid: pd.DataFrame) -> pd.Series | None:
    """Map a heatmap click back to its grid row.

    Streamlit returns the projected ``time`` as epoch ms (UTC), so match on the
    absolute instant (nearest hour in that spot), not an exact tz round-trip.
    """
    raw = getattr(event, "selection", None)
    points = raw.get("cell", []) if hasattr(raw, "get") else []
    if not points:
        return None
    spot_name = points[0].get("spot")
    raw_time = points[0].get("time")
    if spot_name is None or raw_time is None:
        return None
    sel_utc = (
        pd.Timestamp(raw_time, unit="ms", tz="UTC")
        if isinstance(raw_time, (int, float))
        else pd.to_datetime(raw_time, utc=True)
    )
    rows = grid[grid["spot"] == spot_name]
    if rows.empty:
        return None
    delta = (rows["time"].dt.tz_convert("UTC") - sel_utc).abs()
    return rows.loc[delta.idxmin()]


def _timeseries_x_domain(
    prediction_end: pd.Timestamp | None, now: pd.Timestamp
) -> list[pd.Timestamp] | None:
    """Shared x domain for the two time-series charts: [now - 24h, prediction end].

    The right edge is the heatmap grid's last hour (its pinned domain's right
    edge), so the two charts and the heatmap all read one clock (R5); the
    quality chart's older history clips out of frame. None when there is no
    prediction window to bound the axis.
    """
    if prediction_end is None:
        return None
    return [now - pd.Timedelta(hours=24), prediction_end]


def _sync_slider_to_heatmap_click(
    clicked_time: pd.Timestamp, clicked_spot_id: str, options: list[pd.Timestamp]
) -> None:
    """Push a heatmap click's hour and spot onto shared session-state keys.

    Writing "wind_map_hour" and "rider_focus_spot" here is legal: the console
    renders before the slider and switcher buttons are instantiated later in
    this same script run. But a fragment rerun of the console does not
    re-run the map fragment, so an actual change also needs an explicit
    app-scope rerun. Guarded by heat_hour_applied and heat_spot_applied -- a
    run that already applied this exact click does not write or rerun
    again, which is what keeps this from looping. ``options`` is the slider's
    prediction-window hour list, so the clamped hour is always a valid option.
    """
    clamped = _clamp_to_slider_option(clicked_time, options)
    hour_changed = (
        clamped is not None and st.session_state.get("heat_hour_applied") != clamped
    )
    spot_changed = st.session_state.get("heat_spot_applied") != clicked_spot_id
    if not hour_changed and not spot_changed:
        return
    if hour_changed:
        st.session_state["wind_map_hour"] = clamped
        st.session_state["heat_hour_applied"] = clamped
        # Pre-sync the map's own mirror so its guard is already quiet once the
        # forced rerun below reaches it -- otherwise it would fire a second,
        # redundant app rerun for the same change.
        st.session_state["wind_map_hour_seen"] = clamped
    st.session_state["rider_focus_spot"] = clicked_spot_id
    st.session_state["heat_spot_applied"] = clicked_spot_id
    st.rerun(scope="app")


def _render_detail_panel(row: pd.Series, min_kts: float) -> None:
    """Detail card below the heatmap for the selected spot and hour."""
    spot_id = str(row["spot_id"])
    spot_cfg = next((s for s in get_spots() if s["id"] == spot_id), None)
    spot_name = spot_cfg["name"] if spot_cfg else str(row.get("spot", spot_id))
    local_time = row["time"].strftime("%a %d %b %H:%M")
    quality = int(row["quality"])

    # Wind, gusts, and direction reuse the map's cached per-spot frame (no new
    # fetch) so the dial matches the map; match the clicked hour in UTC (<=1 h).
    frame = _spot_wind_frame(spot_id)
    wind = gust = direction = None
    if not frame.empty:
        idx = frame.index
        idx = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
        target = row["time"].tz_convert("UTC")
        pos = int(idx.get_indexer(pd.DatetimeIndex([target]), method="nearest")[0])
        if pos >= 0 and abs((idx[pos] - target).total_seconds()) <= 5400:
            src = frame.iloc[pos]
            wind, gust = float(src["wind_speed_10m"]), float(src["wind_gusts_10m"])
            direction = float(src["wind_direction_10m"])

    have_wind = wind is not None and not pd.isna(wind)
    have_dir = direction is not None and not pd.isna(direction)

    left, right = st.columns([3, 2])
    with left:
        st.markdown(f"**{spot_name}** — {local_time}")
        st.markdown(f"Quality: **{quality}/5** ({quality_label(float(quality))})")
        if have_wind:
            st.markdown(f"Wind: **{wind:.0f} km/h**")
        if gust is not None and not pd.isna(gust):
            st.markdown(f"Gusts: **{gust:.0f} km/h**")
        if have_dir:
            st.markdown(f"Direction: **{_compass(direction)} ({direction:.0f}°)**")
    with right:
        if have_wind and have_dir:
            shore = float(spot_cfg["shore_orientation_deg"]) if spot_cfg else 0.0
            st.markdown(
                wind_dial_svg(
                    direction_deg=direction,
                    speed_kn=wind / _KN_TO_KMH,
                    gust_kn=(gust or 0.0) / _KN_TO_KMH,
                    shore_orientation_deg=shore,
                    min_kts=min_kts,
                ),
                unsafe_allow_html=True,
            )
            st.caption("Needle points downwind; length is speed (to 30 kn).")
        else:
            st.caption("Wind or direction unavailable for this hour — dial hidden.")


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

    # Prediction-window hours shared with the wind-map slider (R6): the heat
    # grid's hour list, filled once the grid is built below. Empty when there
    # is no focus spot / grid, so the slider falls back to the wind-frame hours.
    pred_hours: list[pd.Timestamp] = []

    if focus_spot_id is not None:
        spot_cfg = next(s for s in get_spots() if s["id"] == focus_spot_id)
        spot_lat, spot_lon = float(spot_cfg["lat"]), float(spot_cfg["lon"])
        display_tz = get_api_config()["open_meteo"]["timezone"]
        predictions_list = dashboard_data.get("predictions", [])

        # All-spots session-quality heatmap: every ranked spot on one grid so
        # they compare at a glance, best spot on the top row. No night shading
        # here - daylight is already baked into the score.
        ranked_meta = [
            {
                "spot_id": s["spot_id"],
                "quality_label": s["quality_label"],
                "quality_index": round(float(s["quality_index"]), 2),
                "rideable_hours": int(s["rideable_hours"]),
                "drive_minutes": round(float(s["drive_minutes"]), 1),
                "session_hours": round(float(s["session_hours"]), 1),
                "ride_drive_ratio": round(float(s["ride_drive_ratio"]), 2),
                "score": round(float(s["score"]), 3),
            }
            for s in ranked_spots
        ]
        heat_grid = all_spots_quality_grid(
            tuple(spot["spot_id"] for spot in ranked_spots),
            json.dumps(predictions_list, default=str),
            display_tz,
            json.dumps(ranked_meta),
        )
        # ONE CLOCK: derive the prediction window once from the grid so the
        # heatmap's pinned x domain, both time-series domains (R5), and the
        # wind-map slider options (R6) all read the same hours. Empty grid ->
        # no window; the charts and slider fall back to their own extents.
        if not heat_grid.empty:
            pred_hours = sorted(heat_grid["time"].drop_duplicates())
        prediction_end = heat_grid["time_end"].max() if not heat_grid.empty else None
        # Evaluate "now" in the display timezone (prediction_end's tz) so the
        # shared domain's left edge matches the Europe/Zurich data on the right.
        now = (
            pd.Timestamp.now(tz=prediction_end.tz)
            if prediction_end is not None
            else pd.Timestamp.now(tz="UTC")
        )
        ts_domain = _timeseries_x_domain(prediction_end, now)
        x_scale = (
            alt.Scale(domain=ts_domain, nice=False)
            if ts_domain is not None
            else alt.Undefined
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
            # The deployed vega-tooltip renders the field titled "title" as the
            # bubble header and the one titled "image" as an <img>; in vega-lite
            # the tooltip datum key is the field title, so those titles are load
            # bearing. The rest are label:value rows in this order.
            tooltip = [
                alt.Tooltip("header:N", title="title"),
                alt.Tooltip("dial:N", title="image"),
                alt.Tooltip("quality:O", title="Quality (1-5)"),
            ]
            if "wind" in heat_grid.columns:
                tooltip.append(alt.Tooltip("wind:Q", title="Wind (km/h)", format=".0f"))
            if "gust" in heat_grid.columns:
                tooltip.append(
                    alt.Tooltip("gust:Q", title="Gusts (km/h)", format=".0f")
                )
            tooltip += [
                alt.Tooltip("direction:N", title="Direction"),
                alt.Tooltip("quality_label:N", title="Signal"),
                alt.Tooltip("quality_index:Q", title="Peak quality", format=".2f"),
                alt.Tooltip("rideable_hours:Q", title="Rideable hrs", format=".0f"),
                alt.Tooltip("drive_minutes:Q", title="Drive min", format=".1f"),
                alt.Tooltip("session_hours:Q", title="Session hrs", format=".1f"),
                alt.Tooltip("ride_drive_ratio:Q", title="Ride/drive", format=".2f"),
                alt.Tooltip("score:Q", title="Score", format=".3f"),
            ]

            st.subheader("All spots — session quality")
            st.markdown(_quality_legend_html(), unsafe_allow_html=True)
            cell_select = alt.selection_point(
                name="cell", fields=["spot", "time"], on="click", empty=False
            )
            # Pin the x domain to the grid's own extent so no layered mark (the
            # map-hour rule below) can ever stretch the band width -- this was
            # the bug: an out-of-window slider hour widened the implicit
            # domain and compressed every cell.
            domain_start = heat_grid["time"].min()
            domain_end = prediction_end
            heatmap_layer = (
                alt.Chart(heat_grid)
                .mark_rect()
                .encode(
                    x=alt.X(
                        "time:T",
                        axis=_HEATMAP_X_AXIS,
                        scale=alt.Scale(domain=[domain_start, domain_end], nice=False),
                    ),
                    x2="time_end:T",
                    y=alt.Y(
                        "spot:N",
                        title=None,
                        sort=rank_order,
                        axis=alt.Axis(orient="right", labelFontSize=13),
                    ),
                    # Level 1 must stay INSIDE the scale domain: an out-of-domain
                    # value gives Vega an undefined fill and the mark neither
                    # renders nor hit-tests (a flat week then draws nothing at
                    # all). "transparent" is a defined fill, so the cell keeps
                    # its stroke and stays hover- and clickable.
                    color=alt.Color(
                        "quality:O",
                        scale=alt.Scale(
                            domain=[1, 2, 3, 4, 5],
                            range=["transparent", *_QUALITY_RAMP],
                        ),
                        legend=None,
                    ),
                    # Selected cell gets a full-opacity ink stroke; the rest keep
                    # the hairline surface gap, so the pick is unmistakable.
                    stroke=alt.condition(
                        cell_select, alt.value(rgb_to_hex(INK)), alt.value(_HEATMAP_GAP)
                    ),
                    strokeWidth=alt.condition(
                        cell_select, alt.value(2.5), alt.value(1.0)
                    ),
                    tooltip=tooltip,
                )
                .add_params(cell_select)
            )
            # Direction (b) of the link: a rule at the map's current hour. A
            # slider drag only reruns the map fragment, but that fragment
            # forces an app-scope rerun on a real change (see
            # _wind_map._render_map_fragment), so this fragment redraws too.
            # The rule only layers when the hour falls inside the pinned x
            # domain -- outside it, the domain stays fixed and the rule is
            # just skipped rather than stretching the band (R6/J1).
            map_hour = st.session_state.get("wind_map_hour")
            heatmap = heatmap_layer
            if map_hour is not None:
                grid_tz = heat_grid["time"].dt.tz
                rule_x = (
                    map_hour.tz_convert(grid_tz)
                    if grid_tz is not None and map_hour.tzinfo is not None
                    else map_hour
                )
                if domain_start <= rule_x <= domain_end:
                    highlight = (
                        alt.Chart(pd.DataFrame({"x": [rule_x]}))
                        .mark_rule(color=rgb_to_hex(INK), strokeWidth=2, opacity=0.55)
                        .encode(x="x:T")
                    )
                    heatmap = heatmap_layer + highlight
            heatmap = (
                heatmap.properties(
                    height=_HEATMAP_ROW_PX * max(len(rank_order), 1),
                    background="transparent",
                )
                .configure_view(strokeWidth=0, fill=None)
                .configure_axis(
                    domainColor="#3b5a5a",
                    labelColor="#07252a",
                    titleColor="#07252a",
                )
            )
            event = st.altair_chart(
                heatmap,
                use_container_width=True,
                theme=None,
                on_select="rerun",
                key="quality_heatmap_select",
            )
            selected = _selected_heat_cell(event, heat_grid)
            if selected is not None:
                _sync_slider_to_heatmap_click(
                    selected["time"], str(selected["spot_id"]), pred_hours
                )
            if selected is None:
                st.caption("Click a heatmap cell to inspect that spot and hour.")
            else:
                _render_detail_panel(selected, _minimum_rideable_kts())

        # Quality index timeline
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
                        clip=True,
                    )
                    .encode(
                        x=alt.X("time:T", title="Day", axis=_DAY_AXIS, scale=x_scale),
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
                .mark_rule(color="#ff7a26", strokeWidth=2, clip=True)
                .encode(x=alt.X("x:T", scale=x_scale))
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
                x_scale,
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
                    labelFontSize=13,
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
                x_scale,
            )

            def wind_layer(data: pd.DataFrame, dim: bool) -> alt.Chart:
                return (
                    alt.Chart(data)
                    .mark_line(
                        interpolate="monotone",
                        strokeWidth=1.6 if dim else 2.2,
                        opacity=0.3 if dim else 1.0,
                        clip=True,
                    )
                    .encode(
                        x=alt.X("time:T", title="Day", axis=_DAY_AXIS, scale=x_scale),
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
                .mark_rule(color="#ff7a26", strokeWidth=2, clip=True)
                .encode(x=alt.X("x:T", scale=x_scale))
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
                    clip=True,
                )
                .encode(x=alt.X("time:T", scale=x_scale), y="solar:Q")
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
                    labelFontSize=13,
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

    st.divider()

    render_wind_map(ranked_spots, _minimum_rideable_kts(), pred_hours)
