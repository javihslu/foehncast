"""Rider console: session-quality board, wind chart, spot switcher, ranked grid."""

from __future__ import annotations

import base64
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
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
    quality_bucket,
    quality_label,
)
from foehncast.solar import is_daylight, night_intervals, solar_elevation_deg

from _dial_svg import wind_dial_svg
from _dial_tokens import dial_tokens, rgb_to_hex
from _theme import Palette, active, is_dark, palette, tint
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


# Geometry of the unified time panel. Its views are layered, which Streamlit
# reads as a nested composition: such charts render at their natural size
# instead of stretching to the column, so the plot width is fixed here and
# every view in the vconcat repeats it, which is also what keeps the two plots
# and the two rulers aligned column for column.
_PANEL_PLOT_WIDTH = 480
_PANEL_SPACING_PX = 6
_RULER_HEIGHT_PX = 14
_WIND_HEIGHT_PX = 240


def _heatmap_tick_count(domain_start: pd.Timestamp, domain_end: pd.Timestamp) -> int:
    """Tick-count hint scaled to the pinned window, at least 2.

    2 h rhythm up to a day (the serving horizon is ~14 h), 6 h up to three
    days, 12 h beyond, so hourly cells stay mappable on short windows and a
    multi-day board is not flooded with hour labels.
    """
    hours = (domain_end - domain_start).total_seconds() / 3600
    if hours <= 24:
        spacing = 2
    elif hours <= 72:
        spacing = 6
    else:
        spacing = 12
    return max(2, round(hours / spacing) + 1)


# Midnight ticks render the weekday + day-of-month, the rest just the hour, so
# the day boundary reads off the ruler without a second axis row.
_RULER_LABEL_EXPR = (
    "timeFormat(datum.value, '%H') == '00' "
    "? timeFormat(datum.value, '%a %d') "
    ": timeFormat(datum.value, '%H')"
)


def _ruler_axis(
    orient: str, domain_start: pd.Timestamp, domain_end: pd.Timestamp
) -> alt.Axis:
    """One edge of the panel's time ruler: ticks and labels, no grid.

    The plots inside the panel carry no x axis of their own; this axis is drawn
    once above and once below them, so the whole panel reads as a measured
    strip. The tickCount must stay numeric: the {"interval": ...} form crashes
    the bundled Vega on these layered, domain-pinned views (verified live on
    Streamlit 1.57).
    """
    return alt.Axis(
        orient=orient,
        tickCount=_heatmap_tick_count(domain_start, domain_end),
        labelExpr=_RULER_LABEL_EXPR,
        labelAngle=0,
        grid=False,
        labelFontSize=12,
        labelPadding=3,
        tickSize=5,
        title=None,
    )


# One-hue ramp for the ordered elevation series; gusts differ by dash too.
# Values live in _theme so the dark mode gets its own validated steps.
def _elevation_colors(pal: Palette) -> dict[str, str]:
    return dict(zip(("10m", "80m", "120m", "gusts"), pal.series, strict=True))


# Ordinal 4-step teal ramp for the all-spots session-quality heatmap, covering
# levels 2-5 (light to dark). Level 1 gets no ramp color at all: the dataviz
# validator (--ordinal mode, page surface #eaf3ef) proved a background-
# matching FILL cannot clear the 2:1 light-end floor, so a "1" cell maps to
# "transparent" in the color scale (in-domain, so it still renders its stroke
# and hit-tests). This four-step range passes: monotone lightness, visible
# step gaps, 2.18:1 light end, 2 deg hue spread.
# (values in _theme.Palette.quality, per mode)

# Night cells sit OFF the quality ramp entirely. A cell whose hour has the sun
# below the horizon carries no rideable level, so painting it in any ramp step
# would claim a session that cannot happen. Dimming a ramp step is not an option
# either: a dimmed level 5 lands at the lightness of level 2 or 3 and reads as a
# weaker but real session.
#
# The hue is picked, not eyeballed. Run against the ramp with the dataviz
# validator (--pairs all, light surface #eaf3ef), this is the only candidate that
# PASSES colorblind separation: worst pair vs any ramp step is dE 9.5 (protan),
# 10.3 (tritan). Mid-lightness greys and violets all failed — under deuteranopia
# they collapse onto the ramp (a grey #9aa6ac sits dE 1.0 from level 2, i.e.
# indistinguishable). Lightness, not hue, is what survives CVD, so night has to
# leave the ramp's lightness range. It goes to the LIGHT end deliberately: the
# residual confusion is night-vs-level-1 ("nothing happening"), which still reads
# as don't-go, whereas a dark night tone risks being mistaken for level 5.
# Contrast vs surface is 1.5:1, which the validator flags as needing relief in
# another channel — hence the legend chip and the tooltip's Daylight row, so
# night is never signalled by color alone.
# (value in _theme.Palette.night_fill, per mode)


def _heatmap_gap(pal: Palette) -> str:
    """Hairline between heatmap cells: faint ink, not the surface tone.

    Level-1 cells are fill-free, so a surface-toned stroke would vanish and the
    flat-week "outline board" with it. Faint ink keeps the gridwork visible in
    either mode while still reading as a gap between filled cells.
    """
    r, g, b = pal.rgb(pal.ink)
    return (
        f"rgba({r}, {g}, {b}, 0.16)"
        if pal.name == "light"
        else f"rgba({r}, {g}, {b}, 0.28)"
    )


def _quality_fill(pal: Palette) -> alt.Condition:
    """Continuous fill for a heatmap cell: the hour's own quality, one hue.

    The ramp keeps the two properties the discrete scale existed to protect.
    The low anchor is the first validated step at zero alpha, so a level-1 hour
    still renders as the bare surface -- a fill that pale cannot clear the
    light-end floor -- and the fade through the hue reads as "barely" rather
    than claiming a session. Night never enters the scale: it takes the
    off-ramp night_fill outright, or a windy 02:00 would paint the same green
    as a rideable afternoon. clamp pins out-of-range values to the anchors.
    """
    return alt.condition(
        "datum.is_day",
        alt.Color(
            "hour_quality:Q",
            scale=alt.Scale(
                domain=[1, 2, 3, 4, 5],
                range=[tint(pal.quality[0], 0.0), *pal.quality],
                clamp=True,
            ),
            legend=None,
        ),
        alt.value(pal.night_fill),
    )


# Notice chip shown when the whole window is level 1: the outline board is
# real data (a quiet week), not a render failure, and the chip says so.
_FLAT_WEEK_CHIP = (
    '<span style="display:inline-block;font-family:Manrope,sans-serif;'
    "font-size:0.72rem;color:var(--muted);background:var(--panel);"
    "border:1px solid var(--line);border-radius:999px;"
    'padding:0.1rem 0.6rem;margin:0.15rem 0 0.35rem">'
    "Quiet week — no spot rises above level 1 in daylight this window</span>"
)


def _flat_week(heat_grid: pd.DataFrame) -> bool:
    """True when the window has daylight but no daylight cell rises above level 1.

    Night cells are excluded: they render off-ramp, so a strong 02:00 would
    otherwise suppress the quiet-week chip on a board with nothing rideable in it.
    """
    if heat_grid.empty:
        return False
    daylight = heat_grid[heat_grid["is_day"]]
    return (not daylight.empty) and int(daylight["quality"].max()) <= 1


_LEGEND_CHIP = (
    '<span style="display:inline-block;width:0.7rem;height:0.7rem;'
    "border-radius:2px;{swatch};margin:0 0.3rem 0 0.9rem;"
    'vertical-align:-0.05rem"></span>{level}'
)


def _quality_legend_html() -> str:
    """Manual legend for the heatmap: a gradient strip plus the night swatch.

    The fill is a continuous ramp on the hour's own quality, so the legend is a
    strip through the validated anchors -- fading to the bare surface at the
    level-1 end, where a fill that pale could not clear the light-end floor --
    rather than one chip per level. A Vega legend cannot draw the zero-alpha
    fade, so this is built by hand, mirroring the wind map's chip row
    (_wind_map.render_wind_map).
    """
    ramp = ", ".join([tint(active().quality[0], 0.0), *active().quality])
    strip = (
        '<span style="display:inline-block;width:3.6rem;height:0.7rem;'
        "border-radius:2px;border:1px solid var(--line);"
        f"background:linear-gradient(90deg, {ramp});"
        'margin:0 0.3rem 0 0.9rem;vertical-align:-0.05rem"></span>'
    )
    night = _LEGEND_CHIP.format(
        swatch=f"background:{active().night_fill}", level="Night"
    )
    return (
        "<p style=\"color:var(--ink);font-family:'Manrope',sans-serif;"
        'font-size:0.8rem;font-weight:600;margin:0 0 0.4rem 0">'
        f"Session quality (1-5) 1{strip}5{night}</p>"
    )


def _elevation_legend_html(timeline_frame: pd.DataFrame, title: str) -> str:
    """Series key for the wind plot, drawn in HTML rather than by Vega.

    A Vega legend would have to sit inside one of the panel's views, and the
    panel lays its views out flush so their time axes align -- anything drawn
    outside a view's plot area lands on its neighbour. So the key moves out of
    the composite entirely, and carries the title the wind plot used to have.
    """
    colors = _elevation_colors(active())
    present = [e for e in colors if e in set(timeline_frame["elevation"])]
    chips = []
    for name in present:
        dash = "dashed" if name == "gusts" else "solid"
        chips.append(
            '<span style="display:inline-block;width:1.5rem;'
            f"border-top:3px {dash} {colors[name]};"
            'margin:0 0.35rem 0 0.9rem;vertical-align:0.28rem"></span>'
            f"{name}"
        )
    return (
        "<p style=\"color:var(--ink);font-family:'Manrope',sans-serif;"
        'font-size:0.8rem;font-weight:600;margin:0 0 0.5rem 0">'
        f"{title}{''.join(chips)}</p>"
    )


# Row height per spot; the grid grows with the spot count and the container
# takes the x-axis band, so the axis labels never get clipped.
_HEATMAP_ROW_PX = 30

# Compact wind dial embedded per heatmap cell as a base64 data URI; small since
# it renders inside a hover bubble. Spot-level metric columns the tooltip pulls
# from ranked_spots, constant per spot but carried on every cell row -- so each
# one has to be LABELLED as a spot figure, or an hourly tooltip implies the
# number describes that hour. "score" is gone from here: it is the spot's
# ranking number, it cannot vary by hour by construction, and the cell's own
# hour_quality is what an hourly tooltip should show.
_TOOLTIP_DIAL_PX = 120
_SPOT_METRIC_KEYS = (
    "quality_label",
    "quality_index",
    "rideable_hours",
    "drive_minutes",
    "session_hours",
    "ride_drive_ratio",
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
    """Altair layer obscuring night hours with the off-ramp night hue.

    Same night_fill the heatmap's night cells carry, at wash opacity so the
    wind series still read across it -- one night hue across both plots.
    Clipped and sharing the caller's pinned x scale so a night band reaching
    past the shared domain neither draws outside the plot nor stretches it.
    The axis is suppressed like every other layer in the panel: the two rulers
    are the only time axis.
    """
    return (
        alt.Chart(_night_bands(t_min, t_max, lat, lon))
        .mark_rect(color=active().night_fill, opacity=0.4, clip=True)
        .encode(x=alt.X("x:T", axis=None, scale=x_scale), x2="x2:T")
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
                # The archive is requested by date, so the response runs to the
                # end of the current day and its trailing hours have not
                # happened yet. Nothing can be observed in the future, so drop
                # them rather than drawing them as measurements.
                obs_frame = obs_frame[obs_frame["time"] <= now]
                if not obs_frame.empty:
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


#: How far the predicted quality may sit from the observed one before the hour
#: counts as a miss. The index runs 0-5, so a whole band is the honest cut.
_ACCURACY_MISS_THRESHOLD = 1.0


@st.cache_data(ttl=1800, show_spinner=False)
def all_spots_accuracy(
    spot_ids: tuple[str, ...], predictions_json: str
) -> pd.DataFrame:
    """Past predicted-vs-observed quality per spot, for the heatmap's row marks.

    Reuses the per-spot timeline the ride-quality panel used to draw, so this
    introduces no call the console was not already making -- it makes it for
    every spot rather than only the focused one. Both layers are cached for
    half an hour, which is what keeps that widening affordable.

    Only hours carrying BOTH a past prediction and an observation survive: an
    hour with one and not the other says nothing about accuracy.
    """
    frames: list[pd.DataFrame] = []
    for spot_id in spot_ids:
        timeline = spot_quality_timeline(spot_id, predictions_json)
        if timeline.empty:
            continue
        wide = timeline.pivot_table(
            index="time", columns="series", values="quality_index", aggfunc="mean"
        )
        if not {"Predicted (past)", "Observed"}.issubset(wide.columns):
            continue
        pair = wide[["Predicted (past)", "Observed"]].dropna()
        if pair.empty:
            continue
        frames.append(
            pd.DataFrame(
                {
                    "spot_id": spot_id,
                    "time": pair.index,
                    "predicted": pair["Predicted (past)"].to_numpy(),
                    "observed": pair["Observed"].to_numpy(),
                }
            )
        )
    if not frames:
        return pd.DataFrame(
            columns=["spot_id", "time", "predicted", "observed", "delta", "verdict"]
        )
    out = pd.concat(frames, ignore_index=True)
    out["delta"] = (out["predicted"] - out["observed"]).abs()
    out["verdict"] = out["delta"].map(
        lambda d: "missed" if d > _ACCURACY_MISS_THRESHOLD else "matched"
    )
    return out


def prewarm_spot_caches(spot_ids: list[str], predictions_json: str) -> None:
    """Pre-warm timeline caches for all spots in parallel.

    Calls focus_spot_timeline, spot_quality_timeline, and _spot_wind_frame for
    each spot concurrently so that switching spots is instant and the all-spots
    quality grid finds every per-spot wind frame already cached.
    """
    # Warm the shared prediction history cache first (single BigQuery read)
    # before spawning per-spot threads.
    _prediction_history_cached()

    def _warm(spot_id: str) -> None:
        focus_spot_timeline(spot_id)
        spot_quality_timeline(spot_id, predictions_json)
        _spot_wind_frame(spot_id)

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
    is_day: bool = True,
    pal: Palette | None = None,
) -> str:
    """Base64 SVG data URI of the compact wind dial for one cell, or "".

    Empty when wind or direction is missing so the tooltip just drops the image.
    The base64 alphabet has no raw ``&`` or ``<``, so the URI is tooltip-safe.
    The palette is passed in rather than resolved here, since the caller caches
    the result and has to key on the mode.
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
        is_day=is_day,
        pal=pal,
    )
    b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"


@st.cache_data(ttl=1800, show_spinner=False)
def all_spots_quality_grid(
    spot_ids: tuple[str, ...],
    predictions_json: str,
    display_tz: str,
    ranked_json: str,
    dark: bool,
) -> pd.DataFrame:
    """Hourly quality band (1-5) per spot over the forecast window, with tooltip payload.

    dark is an argument rather than read inside, so the cache keys on it. The
    frame carries theme-resolved dial SVGs and the cache is process-global, so
    resolving the mode in here would serve one viewer the other mode's dials
    for the rest of the TTL.

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
    pal = palette(dark)

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
                # The cell's OWN quality, kept alongside its bucket. The tooltip
                # used to show the spot-level ranking score here, which is
                # constant across the row and so could not describe an hour.
                "hour_quality": [float(r["quality_index"]) for r in forecast_rows],
            }
        )
        frame["spot_id"] = spot_id
        frame["hour"] = frame["time"].dt.floor("h")

        # Daylight is per spot, per hour: rank_spots already drops dark hours
        # from the score, but every hour still gets a cell here, so the grid has
        # to carry its own flag or it paints unrideable darkness as a session.
        cfg = spots_cfg.get(spot_id)
        frame["is_day"] = (
            is_daylight(
                float(cfg["lat"]), float(cfg["lon"]), pd.DatetimeIndex(frame["time"])
            ).to_numpy()
            if cfg
            else True
        )

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

    # "daylight" carries the day/night fact in words for the tooltip, so night
    # never rests on color alone; the fill encoding (_quality_fill) reads
    # is_day directly and never lets a dark hour onto the ramp.
    grid["daylight"] = grid["is_day"].map(
        {True: "Day", False: "Night — sun below horizon"}
    )

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
        _compact_dial_uri(d, w, g, s, min_kts, bool(day), pal)
        for d, w, g, s, day in zip(
            grid["direction"].to_numpy(),
            wind_vals,
            gust_vals,
            shore.to_numpy(),
            grid["is_day"].to_numpy(),
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


def _panel_x_domain(
    heat_grid: pd.DataFrame, timeline_frame: pd.DataFrame
) -> list[pd.Timestamp] | None:
    """The one x domain every view in the time panel is pinned to.

    The heatmap's own extent wins. Its cells are rects, so widening the domain
    to reach further back would compress every one of them -- the bug the
    pinned domain exists to prevent -- and the wind series simply clips to it
    instead. With no grid the wind timeline's own extent stands in; with
    neither there is no panel to draw.
    """
    if not heat_grid.empty:
        return [heat_grid["time"].min(), heat_grid["time_end"].max()]
    if not timeline_frame.empty:
        return [timeline_frame["time"].min(), timeline_frame["time"].max()]
    return None


def _epoch_ms(times: Any) -> list[int]:
    """Epoch milliseconds for a series of timestamps.

    The panel's hover and click params match on this integer rather than on the
    timestamp, so a rule drawn from one dataset can be driven by a pointer over
    another without leaning on temporal equality across datasets.
    """
    return [int(pd.Timestamp(t).value // 1_000_000) for t in times]


def _time_spine(domain_start: pd.Timestamp, domain_end: pd.Timestamp) -> pd.DataFrame:
    """One row per hour of the panel window: its shared hit target and ruler data.

    t_mid is the centre of the hour cell. The board draws an hour as a rect
    spanning it, so anything that marks "this hour" as a point -- the crosshair,
    the pin, a series reading -- sits at the middle, not on the cell's left edge.
    """
    hours = pd.date_range(
        domain_start.floor("h"), domain_end.ceil("h"), freq="h", inclusive="left"
    )
    return pd.DataFrame(
        {
            "time": hours,
            "time_end": hours + pd.Timedelta(hours=1),
            "t_mid": hours + pd.Timedelta(minutes=30),
            "t_ms": _epoch_ms(hours),
        }
    )


def _pinned_panel_time(
    stored: pd.Timestamp | None, domain_start: pd.Timestamp, domain_end: pd.Timestamp
) -> pd.Timestamp | None:
    """The session's pinned hour in the panel's timezone, or None when outside it.

    Same guard the old map-hour rule used: an hour past the window is skipped
    rather than drawn, so the domain stays pinned.
    """
    if stored is None:
        return None
    tz = domain_start.tz
    pinned = (
        stored.tz_convert(tz)
        if tz is not None and stored.tzinfo is not None
        else stored
    )
    return pinned if domain_start <= pinned <= domain_end else None


def _pinned_time_from_event(event: Any, tz: Any) -> pd.Timestamp | None:
    """Map a click in the panel's empty space back to its hour.

    The wind plot's hit layer covers the whole time range, so a click that hits
    no heatmap cell still pins a time; it selects the hour's epoch milliseconds,
    which Streamlit hands back unchanged.
    """
    raw = getattr(event, "selection", None)
    points = raw.get("pin_time", []) if hasattr(raw, "get") else []
    if not points:
        return None
    t_ms = points[0].get("t_ms")
    if t_ms is None:
        return None
    stamp = pd.Timestamp(int(t_ms), unit="ms", tz="UTC")
    return stamp.tz_convert(tz) if tz is not None else stamp.tz_localize(None)


def _sync_slider_to_heatmap_click(
    clicked_time: pd.Timestamp, clicked_spot_id: str | None, options: list[pd.Timestamp]
) -> None:
    """Push a panel click's hour, and its spot when it had one, onto session state.

    Writing "wind_map_hour" and "rider_focus_spot" here is legal: the console
    renders before the slider and switcher buttons are instantiated later in
    this same script run. But a fragment rerun of the console does not
    re-run the map fragment, so an actual change also needs an explicit
    app-scope rerun. Guarded by heat_hour_applied and heat_spot_applied -- a
    run that already applied this exact click does not write or rerun
    again, which is what keeps this from looping. ``options`` is the slider's
    prediction-window hour list, so the clamped hour is always a valid option.
    A click on empty panel space carries no spot, so it passes None and moves
    the pinned time alone.
    """
    clamped = _clamp_to_slider_option(clicked_time, options)
    hour_changed = (
        clamped is not None and st.session_state.get("heat_hour_applied") != clamped
    )
    spot_changed = (
        clicked_spot_id is not None
        and st.session_state.get("heat_spot_applied") != clicked_spot_id
    )
    if not hour_changed and not spot_changed:
        return
    if hour_changed:
        st.session_state["wind_map_hour"] = clamped
        st.session_state["heat_hour_applied"] = clamped
        # Pre-sync the map's own mirror so its guard is already quiet once the
        # forced rerun below reaches it -- otherwise it would fire a second,
        # redundant app rerun for the same change.
        st.session_state["wind_map_hour_seen"] = clamped
    if clicked_spot_id is not None:
        st.session_state["rider_focus_spot"] = clicked_spot_id
        st.session_state["heat_spot_applied"] = clicked_spot_id
    st.rerun(scope="app")


def _spot_hour_wind(
    spot_id: str, time: pd.Timestamp
) -> tuple[float | None, float | None, float | None]:
    """Numeric wind, gust, and direction for one spot at one hour.

    Reuses the map's cached per-spot frame (no new fetch) so the dials match
    the map. Nearest hour in UTC, within 90 minutes.
    """
    frame = _spot_wind_frame(spot_id)
    if frame.empty:
        return None, None, None
    idx = frame.index
    idx = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
    target = time.tz_convert("UTC") if time.tzinfo else time.tz_localize("UTC")
    pos = int(idx.get_indexer(pd.DatetimeIndex([target]), method="nearest")[0])
    if pos < 0 or abs((idx[pos] - target).total_seconds()) > 5400:
        return None, None, None
    src = frame.iloc[pos]
    return (
        float(src["wind_speed_10m"]),
        float(src["wind_gusts_10m"]),
        float(src["wind_direction_10m"]),
    )


def _selection_wind(
    row: pd.Series,
) -> tuple[float | None, float | None, float | None]:
    """Wind, gust, and direction for the picked grid row."""
    return _spot_hour_wind(str(row["spot_id"]), row["time"])


_BUBBLE_ROW = (
    '<div style="display:flex;justify-content:space-between;gap:1rem">'
    '<span style="color:var(--muted)">{label}</span><strong>{value}</strong></div>'
)


def _selection_bubble_html(
    spot_name: str,
    local_time: str,
    quality: int,
    wind: float | None,
    gust: float | None,
    direction: float | None,
    is_day: bool = True,
) -> str:
    """Rounded metrics bubble for the selection row."""
    rows = [
        _BUBBLE_ROW.format(
            label="Quality", value=f"{quality}/5 ({quality_label(float(quality))})"
        )
    ]
    # A dark hour still has a wind forecast, and the quality row above still
    # reports it. Say plainly that it is not a session so the number is read as
    # weather rather than as a recommendation.
    if not is_day:
        rows.append(_BUBBLE_ROW.format(label="Daylight", value="Night — no session"))
    if wind is not None and not pd.isna(wind):
        rows.append(_BUBBLE_ROW.format(label="Wind", value=f"{wind:.0f} km/h"))
    if gust is not None and not pd.isna(gust):
        rows.append(_BUBBLE_ROW.format(label="Gusts", value=f"{gust:.0f} km/h"))
    if direction is not None and not pd.isna(direction):
        rows.append(
            _BUBBLE_ROW.format(
                label="Direction", value=f"{_compass(direction)} ({direction:.0f}°)"
            )
        )
    return (
        '<div style="background:var(--panel);'
        "border:1px solid var(--line);border-radius:14px;"
        "padding:0.7rem 0.9rem;font-family:Manrope,sans-serif;"
        'font-size:0.85rem;color:var(--ink)">'
        f'<div style="font-weight:700">{spot_name}</div>'
        f'<div style="color:var(--muted);font-size:0.75rem;margin-bottom:0.45rem">'
        f"{local_time}</div>" + "".join(rows) + "</div>"
    )


def _default_detail_row(
    grid: pd.DataFrame, spot_id: str | None, pinned: pd.Timestamp | None
) -> pd.Series | None:
    """What the details panel shows before anything has been clicked.

    The panel is permanent, so it opens on the pinned hour at the focused spot
    rather than on an empty column. None when there is no pinned hour yet, and
    the panel shows its hint instead.
    """
    if grid.empty or spot_id is None or pinned is None:
        return None
    rows = grid[grid["spot_id"] == spot_id]
    if rows.empty:
        return None
    target = pinned.tz_convert("UTC") if pinned.tzinfo else pinned.tz_localize("UTC")
    delta = (rows["time"].dt.tz_convert("UTC") - target).abs()
    return rows.loc[delta.idxmin()]


def _render_selection_bubble(row: pd.Series) -> None:
    """Metrics bubble for the selected spot and hour, beside the wind plot."""
    spot_id = str(row["spot_id"])
    spot_cfg = next((s for s in get_spots() if s["id"] == spot_id), None)
    spot_name = spot_cfg["name"] if spot_cfg else str(row.get("spot", spot_id))
    local_time = row["time"].strftime("%a %d %b %H:%M")
    wind, gust, direction = _selection_wind(row)
    st.markdown(
        _selection_bubble_html(
            spot_name,
            local_time,
            int(row["quality"]),
            wind,
            gust,
            direction,
            bool(row.get("is_day", True)),
        ),
        unsafe_allow_html=True,
    )


def _dial_tile_html(name: str, dial_svg: str, selected: bool) -> str:
    """One tile of the comparison grid: a compact dial with the spot's name.

    The selected spot wears the reading-orange border and the accent-text name;
    the rest keep a transparent border so every tile holds the same footprint.
    """
    pal = active()
    border = pal.reading if selected else "transparent"
    name_style = (
        f"color:{pal.accent_text};font-weight:700"
        if selected
        else "color:var(--muted);font-weight:600"
    )
    return (
        f'<div style="border:2px solid {border};border-radius:12px;'
        'padding:0.25rem 0.1rem 0.1rem;margin-bottom:0.3rem">'
        f"{dial_svg}"
        f'<div style="text-align:center;font-family:Manrope,sans-serif;'
        f'font-size:0.72rem;{name_style}">{name}</div></div>'
    )


def _render_dial_grid(
    spot_ids: list[str],
    selected_spot_id: str | None,
    hour: pd.Timestamp,
    min_kts: float,
) -> None:
    """Wind dials for every ranked spot at the selected hour, beside the board.

    All spots at one instant, so the selected spot's wind reads against its
    alternatives; the highlight marks which one the details below describe.
    """
    spots_cfg = {s["id"]: s for s in get_spots()}
    st.markdown(
        "<p style=\"color:var(--ink);font-family:'Manrope',sans-serif;"
        'font-size:0.8rem;font-weight:600;margin:0 0 0.4rem 0">'
        f"All spots — {hour.strftime('%a %d %b %H:%M')}</p>",
        unsafe_allow_html=True,
    )
    cols = st.columns(3)
    for i, spot_id in enumerate(spot_ids):
        cfg = spots_cfg.get(spot_id)
        if cfg is None:
            continue
        wind, gust, direction = _spot_hour_wind(spot_id, hour)
        with cols[i % 3]:
            if wind is None or direction is None:
                st.caption(f"{cfg['name']}: no wind data")
                continue
            day = bool(
                is_daylight(
                    float(cfg["lat"]), float(cfg["lon"]), pd.DatetimeIndex([hour])
                ).to_numpy()[0]
            )
            svg = wind_dial_svg(
                direction_deg=direction,
                speed_kn=wind / _KN_TO_KMH,
                gust_kn=(gust or 0.0) / _KN_TO_KMH,
                shore_orientation_deg=float(cfg["shore_orientation_deg"]),
                min_kts=min_kts,
                size_px=92,
                detail="compact",
                is_day=day,
            )
            st.markdown(
                _dial_tile_html(cfg["name"], svg, spot_id == selected_spot_id),
                unsafe_allow_html=True,
            )
    st.caption(
        "Each dial is that spot's wind at the selected hour: the dot's bearing "
        "is where the wind blows toward, its distance from the centre is speed "
        "(to 30 kn), and inside the teal band is a session. The orange frame "
        "marks the selected spot."
    )


@dataclass(frozen=True, eq=False)
class _Panel:
    """What every view in the time panel shares: one clock, one palette, one pointer."""

    spine: pd.DataFrame
    x_scale: alt.Scale
    domain_start: pd.Timestamp
    domain_end: pd.Timestamp
    pal: Palette
    pinned: pd.Timestamp | None
    cell: alt.Parameter
    hover_board: alt.Parameter
    hover_row: alt.Parameter
    hover_wind: alt.Parameter
    pin_time: alt.Parameter


def _heat_tooltip(heat_grid: pd.DataFrame) -> list[alt.Tooltip]:
    """Hover bubble for a heatmap cell.

    The deployed vega-tooltip renders the field titled "title" as the bubble
    header and the one titled "image" as an <img>; in vega-lite the tooltip
    datum key is the field title, so those titles are load bearing. The rest are
    label:value rows in this order.
    """
    tooltip = [
        alt.Tooltip("header:N", title="title"),
        alt.Tooltip("dial:N", title="image"),
        alt.Tooltip("quality:O", title="Quality (1-5)"),
        alt.Tooltip("daylight:N", title="Daylight"),
    ]
    if "wind" in heat_grid.columns:
        tooltip.append(alt.Tooltip("wind:Q", title="Wind (km/h)", format=".0f"))
    if "gust" in heat_grid.columns:
        tooltip.append(alt.Tooltip("gust:Q", title="Gusts (km/h)", format=".0f"))
    return tooltip + [
        alt.Tooltip("direction:N", title="Direction"),
        alt.Tooltip("hour_quality:Q", title="Quality this hour", format=".2f"),
        alt.Tooltip("quality_index:Q", title="Peak quality (spot)", format=".2f"),
        # The label names the spot's best daylight hour, so it is titled for
        # that peak and kept beside it. Called plain "Signal" next to the
        # hourly figure it read as this cell's own verdict.
        alt.Tooltip("quality_label:N", title="Peak signal (spot)"),
        # Daylight-scoped upstream (dashboard counts rideable & daylight), so
        # the label says so rather than implying a round-the-clock count.
        alt.Tooltip("rideable_hours:Q", title="Rideable hrs (day)", format=".0f"),
        alt.Tooltip("drive_minutes:Q", title="Drive min", format=".1f"),
        alt.Tooltip("session_hours:Q", title="Session hrs", format=".1f"),
        alt.Tooltip("ride_drive_ratio:Q", title="Ride/drive", format=".2f"),
    ]


def _pin_frame(pinned: pd.Timestamp) -> pd.DataFrame:
    """The pinned hour and the day+time label the rulers print beside it.

    time_mid centres the pin in its hour cell, matching the spine's t_mid.
    """
    return pd.DataFrame(
        {
            "time": [pinned],
            "time_mid": [pinned + pd.Timedelta(minutes=30)],
            "label": [pinned.strftime("%a %d %b %H:00")],
        }
    )


def _panel_x(panel: _Panel, field: str = "time") -> alt.X:
    """The panel's x channel: the shared domain, and no axis of the layer's own.

    Every layer inside a plot has to suppress its axis, not just the one that
    would have drawn it. A layer that leaves the axis implicit next to a sibling
    that nulls it leaves vega-lite with nothing to merge, and the whole spec
    fails to compile.
    """
    return alt.X(f"{field}:T", axis=None, scale=panel.x_scale)


def _hover_rule(panel: _Panel, param: alt.Parameter) -> alt.Chart:
    """Vertical crosshair at the hovered hour, drawn from the shared spine.

    Both plots draw a rule for both hover params, so the line spans the whole
    panel wherever the pointer is; the param that is not under the pointer
    filters to no rows and draws nothing.
    """
    return (
        alt.Chart(panel.spine)
        .mark_rule(
            color=panel.pal.ink_secondary, strokeWidth=1, opacity=0.85, clip=True
        )
        .encode(x=_panel_x(panel, "t_mid"))
        .transform_filter(param)
    )


def _pin_rule(panel: _Panel) -> alt.Chart:
    """The pinned time selector: a reading-orange rule bisecting the pinned cell."""
    return (
        alt.Chart(_pin_frame(panel.pinned))
        .mark_rule(color=panel.pal.reading, strokeWidth=2, clip=True)
        .encode(x=_panel_x(panel, "time_mid"))
    )


def _ruler_view(panel: _Panel, orient: str) -> alt.Chart:
    """One ruler edge: the shared time axis, plus the pinned label when there is one.

    The label is accent_text rather than the reading orange the rule wears: it
    is text on the page surface, so it has to clear the 4.5:1 floor, which the
    plain mark orange does not.
    """
    axis = _ruler_axis(orient, panel.domain_start, panel.domain_end)
    ruler = (
        alt.Chart(panel.spine)
        .mark_rule(opacity=0)
        .encode(x=alt.X("time:T", axis=axis, scale=panel.x_scale))
    )
    if panel.pinned is None:
        return ruler.properties(height=_RULER_HEIGHT_PX, width=_PANEL_PLOT_WIDTH)
    pin = _pin_frame(panel.pinned)
    tick = (
        alt.Chart(pin)
        .mark_rule(color=panel.pal.reading, strokeWidth=2, clip=True)
        .encode(x=alt.X("time_mid:T", scale=panel.x_scale))
    )
    label = (
        alt.Chart(pin)
        # No font family: the ruler's own labels take the chart default, and a
        # family the renderer does not have drops the glyphs silently.
        .mark_text(
            color=panel.pal.accent_text,
            fontSize=11,
            fontWeight=700,
            align="left",
            baseline="middle",
            dx=5,
        )
        .encode(x=alt.X("time_mid:T", scale=panel.x_scale), text="label:N")
    )
    return alt.layer(ruler, tick, label).properties(
        height=_RULER_HEIGHT_PX, width=_PANEL_PLOT_WIDTH
    )


def _board_view(
    panel: _Panel,
    heat_grid: pd.DataFrame,
    rank_order: list[str],
    accuracy: pd.DataFrame,
    now: pd.Timestamp,
) -> alt.LayerChart:
    """The session-quality board, without an x axis of its own.

    Cells are rects on a continuous x, so each one has to declare where it ends
    (x2) or a later cell paints over its neighbours.
    """
    pal = panel.pal
    tok = dial_tokens(pal)
    cells = (
        alt.Chart(heat_grid)
        .mark_rect()
        .encode(
            x=_panel_x(panel),
            x2="time_end:T",
            y=alt.Y(
                "spot:N",
                title=None,
                sort=rank_order,
                axis=alt.Axis(orient="right", labelFontSize=13),
            ),
            # The cell's own quality drives the fill continuously; night cells
            # leave the ramp entirely. See _quality_fill.
            color=_quality_fill(pal),
            # Selected cell gets a full-opacity ink stroke; the rest keep the
            # hairline surface gap, so the pick is unmistakable.
            stroke=alt.condition(
                panel.cell, alt.value(rgb_to_hex(tok.ink)), alt.value(_heatmap_gap(pal))
            ),
            strokeWidth=alt.condition(panel.cell, alt.value(2.5), alt.value(1.0)),
            tooltip=_heat_tooltip(heat_grid),
        )
        .add_params(panel.cell, panel.hover_board, panel.hover_row)
    )
    layers = [cells]

    # Where the record stops being hindcast and starts being forecast.
    if panel.domain_start <= now <= panel.domain_end:
        layers.append(
            alt.Chart(pd.DataFrame({"x": [now]}))
            .mark_rule(
                color=pal.ink_secondary, strokeWidth=1.5, strokeDash=[5, 3], clip=True
            )
            .encode(x=_panel_x(panel, "x"))
        )

    if not accuracy.empty:
        # A mark on this board can land on any cell -- a dark quality step or
        # the pale night fill -- so no single ink survives both. The casing is
        # the palette's role for exactly that: a halo underneath, drawn first
        # and slightly thicker.
        shape = alt.Shape(
            "verdict:N",
            scale=alt.Scale(domain=["matched", "missed"], range=["circle", "cross"]),
            legend=None,
        )
        layers.append(
            alt.Chart(accuracy)
            .mark_point(size=80, strokeWidth=5, filled=False, clip=True)
            .encode(
                x=_panel_x(panel),
                y=alt.Y("spot:N", sort=rank_order),
                shape=shape,
                color=alt.value(pal.casing),
            )
        )
        layers.append(
            alt.Chart(accuracy)
            .mark_point(size=80, strokeWidth=2.2, filled=False, clip=True)
            .encode(
                x=_panel_x(panel),
                y=alt.Y("spot:N", sort=rank_order),
                # Shape as well as colour: a hollow ring for an hour the model
                # called right, a filled cross where it missed, so the verdict
                # never rests on hue alone.
                shape=shape,
                color=alt.Color(
                    "verdict:N",
                    scale=alt.Scale(
                        domain=["matched", "missed"],
                        range=[pal.ink_secondary, pal.danger],
                    ),
                    legend=None,
                ),
                opacity=alt.condition(
                    alt.datum.verdict == "missed", alt.value(1.0), alt.value(0.85)
                ),
                tooltip=[
                    alt.Tooltip("spot:N", title="Spot"),
                    alt.Tooltip("time:T", title="Hour", format="%a %H:00"),
                    alt.Tooltip("predicted:Q", title="Predicted", format=".2f"),
                    alt.Tooltip("observed:Q", title="Observed", format=".2f"),
                    alt.Tooltip("delta:Q", title="Off by", format=".2f"),
                ],
            )
        )

    # The horizontal half of the crosshair: the hovered row, which on this board
    # is a spot rather than a value.
    layers.append(
        alt.Chart(pd.DataFrame({"spot": rank_order}))
        .mark_rule(color=pal.ink_secondary, strokeWidth=1, opacity=0.85, clip=True)
        .encode(y=alt.Y("spot:N", sort=rank_order))
        .transform_filter(panel.hover_row)
    )
    layers.append(_hover_rule(panel, panel.hover_board))
    layers.append(_hover_rule(panel, panel.hover_wind))
    if panel.pinned is not None:
        layers.append(_pin_rule(panel))

    # Layered charts SHARE the colour and shape scales by default, so
    # "matched"/"missed" would be looked up in the cells' own quality ramp,
    # miss, and paint as undefined -- marks present in the DOM and invisible on
    # screen. Same trap the level-1 note in _quality_fill describes.
    return (
        alt.layer(*layers)
        .resolve_scale(color="independent", shape="independent")
        .properties(
            height=_HEATMAP_ROW_PX * max(len(rank_order), 1), width=_PANEL_PLOT_WIDTH
        )
    )


def _wind_view(
    panel: _Panel,
    timeline_frame: pd.DataFrame,
    spot_lat: float,
    spot_lon: float,
    min_kts: float,
) -> alt.LayerChart:
    """The wind and gust plot, on the board's clock and carrying the panel's hit layer."""
    pal = panel.pal
    frame = timeline_frame.assign(
        is_day=is_daylight(
            spot_lat, spot_lon, pd.DatetimeIndex(timeline_frame["time"])
        ).to_numpy(),
        t_ms=_epoch_ms(timeline_frame["time"]),
        # An hourly value is drawn at the middle of its hour, where the board
        # draws that hour's cell, so the two plots align column for column.
        time_mid=timeline_frame["time"] + pd.Timedelta(minutes=30),
    )
    threshold_kmh = min_kts * _KN_TO_KMH
    elevations = [
        e for e in ("10m", "80m", "120m", "gusts") if e in set(frame["elevation"])
    ]
    colors = _elevation_colors(pal)
    color_scale = alt.Scale(domain=elevations, range=[colors[e] for e in elevations])

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
                x=_panel_x(panel, "time_mid"),
                y=alt.Y(
                    "wind_speed:Q",
                    title="Wind speed (km/h)",
                    axis=alt.Axis(orient="right", labelFontSize=13),
                ),
                color=alt.Color(
                    "elevation:N",
                    scale=color_scale,
                    # The key is drawn in HTML above the panel: see
                    # _elevation_legend_html.
                    legend=None,
                ),
                strokeDash=alt.StrokeDash(
                    "elevation:N",
                    scale=alt.Scale(
                        domain=elevations,
                        range=[[5, 4] if e == "gusts" else [1, 0] for e in elevations],
                    ),
                    legend=None,
                ),
            )
        )

    # Solar-elevation curve along the chart bottom, pre-scaled into wind-speed
    # units so it shares the axis without a second scale.
    strip_times = pd.date_range(
        frame["time"].min().floor("h"), frame["time"].max().ceil("h"), freq="30min"
    )
    elevation = solar_elevation_deg(spot_lat, spot_lon, strip_times).clip(lower=0.0)
    peak = float(elevation.max()) or 1.0
    band_kmh = 0.12 * max(float(frame["wind_speed"].max()), threshold_kmh)
    solar_area = (
        alt.Chart(
            pd.DataFrame(
                {"time": strip_times, "solar": elevation.to_numpy() / peak * band_kmh}
            )
        )
        .mark_area(
            color=pal.quality[2],
            opacity=0.22,
            line={"color": pal.quality[2], "strokeWidth": 1.0},
            clip=True,
        )
        .encode(x=_panel_x(panel), y="solar:Q")
    )
    threshold = (
        alt.Chart(pd.DataFrame({"y": [threshold_kmh]}))
        .mark_rule(color=pal.danger, strokeDash=[4, 4], strokeWidth=1.5)
        .encode(y="y:Q")
    )
    threshold_label = (
        alt.Chart(
            pd.DataFrame(
                {"y": [threshold_kmh], "label": [f"{int(min_kts)} kn rideable"]}
            )
        )
        .mark_text(
            align="left", baseline="bottom", dx=6, dy=-3, color=pal.danger, fontSize=10
        )
        .encode(y="y:Q", text="label:N")
    )

    # At the hovered hour every series shows its own number: a dot on the line
    # and the value beside it. This replaces the old horizontal rule, which
    # only marked the 10 m reading's position without saying what it was.
    def value_marks(param: alt.Parameter) -> list[alt.Chart]:
        base = alt.Chart(frame).transform_filter(param)
        points = base.mark_point(filled=True, size=45, clip=True).encode(
            x=_panel_x(panel, "time_mid"),
            y=alt.Y("wind_speed:Q"),
            color=alt.Color("elevation:N", scale=color_scale, legend=None),
        )
        labels = base.mark_text(
            align="left",
            baseline="middle",
            dx=7,
            fontSize=11,
            fontWeight=700,
            clip=True,
        ).encode(
            x=_panel_x(panel, "time_mid"),
            y=alt.Y("wind_speed:Q"),
            text=alt.Text("wind_speed:Q", format=".0f"),
            color=alt.Color("elevation:N", scale=color_scale, legend=None),
        )
        return [points, labels]

    # Hit layer, on top and invisible: it gives the wind plot the same hourly
    # hover and click targets the board's cells give, so a click on empty space
    # still pins a time. A rect on a continuous x must declare x2.
    hits = (
        alt.Chart(panel.spine)
        .mark_rect(opacity=0)
        .encode(x=_panel_x(panel), x2="time_end:T")
        .add_params(panel.hover_wind, panel.pin_time)
    )

    layers = [
        _night_rect(
            frame["time"].min(), frame["time"].max(), spot_lat, spot_lon, panel.x_scale
        ),
        solar_area,
        # Night hours render dimmed underneath; daylight at full strength.
        wind_layer(frame, dim=True),
        wind_layer(frame[frame["is_day"]], dim=False),
        threshold,
        threshold_label,
        _hover_rule(panel, panel.hover_board),
        _hover_rule(panel, panel.hover_wind),
        *value_marks(panel.hover_board),
        *value_marks(panel.hover_wind),
    ]
    if panel.pinned is not None:
        layers.append(_pin_rule(panel))
    layers.append(hits)
    return alt.layer(*layers).properties(
        height=_WIND_HEIGHT_PX, width=_PANEL_PLOT_WIDTH
    )


def _time_panel(
    heat_grid: pd.DataFrame,
    rank_order: list[str],
    accuracy: pd.DataFrame,
    timeline_frame: pd.DataFrame,
    spot_lat: float,
    spot_lon: float,
    domain: list[pd.Timestamp],
    now: pd.Timestamp,
    pinned: pd.Timestamp | None,
    min_kts: float,
) -> tuple[alt.VConcatChart, list[str]]:
    """The board and the wind plot as one strip, ruled top and bottom.

    Both plots are pinned to the same x domain and the same hourly spine, so
    their columns line up and one crosshair reads across both. Returns the
    composite and the names of the selection params Streamlit should listen to
    -- the hover params must stay out of that list, or every pointer move would
    rerun the app.
    """
    pal = active()
    domain_start, domain_end = domain[0], domain[1]
    panel = _Panel(
        spine=_time_spine(domain_start, domain_end),
        x_scale=alt.Scale(domain=domain, nice=False),
        domain_start=domain_start,
        domain_end=domain_end,
        pal=pal,
        pinned=pinned,
        cell=alt.selection_point(
            name="cell", fields=["spot", "time"], on="click", empty=False
        ),
        hover_board=alt.selection_point(
            name="hover_board",
            fields=["t_ms"],
            on="pointerover",
            clear="pointerout",
            empty=False,
        ),
        hover_row=alt.selection_point(
            name="hover_row",
            fields=["spot"],
            on="pointerover",
            clear="pointerout",
            empty=False,
        ),
        hover_wind=alt.selection_point(
            name="hover_wind",
            fields=["t_ms"],
            on="pointerover",
            clear="pointerout",
            empty=False,
        ),
        pin_time=alt.selection_point(
            name="pin_time", fields=["t_ms"], on="click", empty=False
        ),
    )

    views = [_ruler_view(panel, "top")]
    modes: list[str] = []
    if not heat_grid.empty:
        views.append(_board_view(panel, heat_grid, rank_order, accuracy, now))
        modes.append("cell")
    if not timeline_frame.empty:
        views.append(_wind_view(panel, timeline_frame, spot_lat, spot_lon, min_kts))
        modes.append("pin_time")
    views.append(_ruler_view(panel, "bottom"))

    return (
        alt.vconcat(*views, spacing=_PANEL_SPACING_PX, bounds="flush")
        .properties(
            background="transparent",
            # The y axes sit on the right, so the plot's left edge has no
            # gutter: a midnight "%a %d" ruler label near that edge
            # center-anchors past it and clips. The left padding buys the
            # half-label of room (a padding OBJECT zeroes any side left
            # unspecified, hence all four).
            padding={"left": 26, "top": 6, "right": 6, "bottom": 6},
        )
        .configure_view(strokeWidth=0, fill=None)
        .configure_axis(
            domainColor=pal.ink_secondary,
            gridColor=pal.grid,
            labelColor=pal.ink,
            titleColor=pal.ink,
        ),
        modes,
    )


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
        # they compare at a glance, best spot on the top row. Daylight is baked
        # into the SCORE that orders the rows, but each cell is its own hour, so
        # cells carry the flag themselves and dark hours render off-ramp.
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
            is_dark(),
        )
        # ONE CLOCK: derive the prediction window once from the grid so the
        # panel's pinned x domain -- both plots and both rulers -- and the
        # wind-map slider options (R6) all read the same hours. Empty grid ->
        # no window; the panel falls back to its own extent.
        if not heat_grid.empty:
            pred_hours = sorted(heat_grid["time"].drop_duplicates())
        timeline_frame = focus_spot_timeline(focus_spot_id)
        min_kts = _minimum_rideable_kts()
        domain = _panel_x_domain(heat_grid, timeline_frame)
        # Evaluate "now" in the display timezone (the window's own tz) so the
        # hindcast boundary lands where the Europe/Zurich data says it should.
        now = (
            pd.Timestamp.now(tz=domain[1].tz)
            if domain is not None
            else pd.Timestamp.now(tz="UTC")
        )

        rank_order = [
            spot_lookup[s["spot_id"]]["name"]
            for s in ranked_spots
            if s["spot_id"] in spot_lookup
        ]
        accuracy = all_spots_accuracy(
            tuple(spot["spot_id"] for spot in ranked_spots),
            json.dumps(predictions_list, default=str),
        )
        if not heat_grid.empty:
            heat_grid = heat_grid.assign(
                spot=heat_grid["spot_id"].map(lambda sid: spot_lookup[sid]["name"]),
                # Epoch milliseconds: what the panel's hover and click params
                # match on, so a rule drawn from the spine can be driven by a
                # pointer over a cell.
                t_ms=_epoch_ms(heat_grid["time"]),
            )
        if not accuracy.empty and domain is not None:
            accuracy = accuracy.assign(
                spot=accuracy["spot_id"].map(
                    lambda sid: spot_lookup[sid]["name"] if sid in spot_lookup else sid
                ),
                # Half a cell right, so a mark sits in its hour rather than on
                # the boundary between two.
                time=accuracy["time"].dt.tz_convert(display_tz)
                + pd.Timedelta(minutes=30),
            )
            accuracy = accuracy[
                (accuracy["time"] >= domain[0])
                & (accuracy["time"] <= domain[1])
                & accuracy["spot"].isin(rank_order)
            ]

        if domain is None:
            st.info("No forecast window available for this spot right now.")
        else:
            pinned = _pinned_panel_time(
                st.session_state.get("wind_map_hour"), domain[0], domain[1]
            )
            st.subheader("All spots — session quality")
            st.markdown(_quality_legend_html(), unsafe_allow_html=True)
            if not timeline_frame.empty:
                st.markdown(
                    _elevation_legend_html(
                        timeline_frame,
                        f"Wind & gusts — {spot_label(spot_lookup, focus_spot_id)}",
                    ),
                    unsafe_allow_html=True,
                )
            if _flat_week(heat_grid):
                st.markdown(_FLAT_WEEK_CHIP, unsafe_allow_html=True)

            panel, modes = _time_panel(
                heat_grid,
                rank_order,
                accuracy,
                timeline_frame,
                spot_lat,
                spot_lon,
                domain,
                now,
                pinned,
                min_kts,
            )
            # The details panel holds its column whether or not a cell is
            # picked, so the panel beside it never changes width.
            panel_col, detail_col = st.columns([7, 5], gap="medium")
            with panel_col:
                event = st.altair_chart(
                    panel,
                    theme=None,
                    on_select="rerun",
                    key="time_panel_select",
                    selection_mode=modes,
                )
                st.caption(
                    "Click anywhere in the panel to pin a time; the orange rule "
                    "and the label on both rulers mark it. The green band along "
                    "the wind plot traces solar elevation, scaled to the "
                    "wind-speed axis."
                )
            selected = (
                _selected_heat_cell(event, heat_grid) if not heat_grid.empty else None
            )
            if selected is not None:
                # A cell carries both halves of the pick: the hour and the spot.
                _sync_slider_to_heatmap_click(
                    selected["time"], str(selected["spot_id"]), pred_hours
                )
            else:
                # Empty panel space carries only the hour.
                clicked = _pinned_time_from_event(event, domain[0].tz)
                if clicked is not None:
                    _sync_slider_to_heatmap_click(clicked, None, pred_hours)
            with detail_col:
                detail = (
                    selected
                    if selected is not None
                    else _default_detail_row(heat_grid, focus_spot_id, pinned)
                )
                # The comparison grid sits beside the board, the bubble below it
                # beside the wind plot; both follow the selected spot and hour.
                dial_hour = (
                    detail["time"]
                    if detail is not None
                    else pinned
                    if pinned is not None
                    else _clamp_to_slider_option(now, pred_hours)
                )
                ranked_ids = [s["spot_id"] for s in ranked_spots]
                if dial_hour is not None and ranked_ids:
                    _render_dial_grid(
                        ranked_ids,
                        str(detail["spot_id"]) if detail is not None else focus_spot_id,
                        dial_hour,
                        min_kts,
                    )
                if detail is None:
                    st.caption(
                        "Click a board cell to inspect that spot and hour, or "
                        "anywhere else in the panel to pin a time."
                    )
                else:
                    _render_selection_bubble(detail)
                if not accuracy.empty:
                    missed = int((accuracy["verdict"] == "missed").sum())
                    st.caption(
                        f"Marks left of the dashed line compare past forecasts "
                        f"with what was observed: a ring means the hour was "
                        f"called within {_ACCURACY_MISS_THRESHOLD:.0f} quality "
                        f"band, a cross means it missed "
                        f"({missed} of {len(accuracy)} hours)."
                    )

    st.divider()

    render_wind_map(ranked_spots, _minimum_rideable_kts(), pred_hours)
