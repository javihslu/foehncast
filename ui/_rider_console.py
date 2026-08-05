"""Rider console: session-quality board, wind chart, spot switcher, ranked grid."""

from __future__ import annotations

import base64
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
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
from foehncast.solar import is_daylight_hour, night_intervals, solar_elevation_deg

from _dial_svg import wind_dial_svg
from _dial_tokens import dial_tokens, rgb_to_hex
from _theme import Palette, active, is_dark, palette, tint
from _wind_map import (
    _KN_TO_KMH,
    _clamp_to_slider_option,
    _compass,
    _spot_wind_frame,
    dangerous_kts,
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
_RULER_HEIGHT_PX = 22
_COVERAGE_HEIGHT_PX = 14
_WIND_HEIGHT_PX = 240

# An axis is drawn OUTSIDE the view it belongs to, and the panel lays its views
# out flush, which leaves that band out of the layout. So the panel has to
# reserve it as padding: with the 6 px the other edges use, both rulers' labels
# fell off the canvas and the panel had no readable time scale at all. Two
# label lines plus the tick need this much.
_RULER_AXIS_BAND_PX = 38


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


# Two lines per tick: the clock time always, and the date on the second line
# whenever the tick opens a new day. An array returned from labelExpr is what
# Vega renders as multiple label lines. The window's first day is usually
# already under way, so it has no midnight tick and takes its date from
# _day_label_frame instead.
_RULER_LABEL_EXPR = (
    "[timeFormat(datum.value, '%H:%M'), "
    "timeFormat(datum.value, '%H:%M') == '00:00' "
    "? timeFormat(datum.value, '%a %d %b') : '']"
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


def _day_label_frame(domain_start: pd.Timestamp) -> pd.DataFrame:
    """The date of the window's first day, printed inside the ruler.

    Every later day announces itself on the axis, whose midnight tick carries
    the date on its second label line. The first day is usually already under
    way when the window opens, so without this its date would never be printed.
    """
    if domain_start == domain_start.floor("D"):
        return pd.DataFrame(columns=["time", "label"])
    return pd.DataFrame(
        {"time": [domain_start], "label": [domain_start.strftime("%a %d %b")]}
    )


def _sun_frame(
    domain_start: pd.Timestamp,
    domain_end: pd.Timestamp,
    lat: float,
    lon: float,
) -> pd.DataFrame:
    """Sunrise and sunset instants inside the window, one pair per day.

    Read from the same dusk-to-dawn intervals the wind plot's night bands come
    from (solar.night_intervals): a night starts at sunset and ends at sunrise.
    The bands quantize those edges to whole hourly cells so the two plots agree
    column for column; a sun mark is a time rather than a cell, so it keeps the
    exact instant and can sit inside the last night cell.
    """
    rows = [
        {"time": t, "event": event, "label": f"{event} {t:%a %d %b %H:%M}"}
        for dusk, dawn in night_intervals(lat, lon, domain_start, domain_end)
        for t, event in ((dusk, "Sunset"), (dawn, "Sunrise"))
    ]
    frame = pd.DataFrame(rows, columns=["time", "event", "label"])
    return frame[(frame["time"] >= domain_start) & (frame["time"] <= domain_end)]


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


def _light_green(pal: Palette) -> str:
    """The lightest step of the mode's quality ramp.

    The rideable threshold used to wear the danger red, which read as one more
    selection mark beside the reading orange. It takes a light green instead,
    clearly apart from the saturated green the NOW rule wears. The ramp's
    anchor flips between modes -- level 1 sits nearest the surface -- so the
    lightest step is the first in light mode and the last in dark.
    """
    return pal.quality[0] if pal.name == "light" else pal.quality[3]


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
    """Night rectangles for the spot, quantized to the panel's hourly cells.

    Built from the same per-hour daylight rule the heatmap cells use
    (is_daylight_hour), so the wash and the night cells start and end on the
    same column edges. Exact sunrise/sunset instants would sit up to an hour
    inside a cell and read as the two plots disagreeing about the night.
    """
    hours = pd.date_range(t_min.floor("h"), t_max.ceil("h"), freq="h", inclusive="left")
    if hours.empty:
        return pd.DataFrame(columns=["x", "x2"])
    day = is_daylight_hour(lat, lon, hours).to_numpy()
    spans: list[dict[str, pd.Timestamp]] = []
    open_i: int | None = None
    for i, lit in enumerate(day):
        if not lit and open_i is None:
            open_i = i
        if lit and open_i is not None:
            spans.append({"x": hours[open_i], "x2": hours[i]})
            open_i = None
    if open_i is not None:
        spans.append({"x": hours[open_i], "x2": hours[-1] + pd.Timedelta(hours=1)})
    return pd.DataFrame(spans)


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

#: Columns of the per-spot, per-hour accuracy frame. "coverage" says which
#: halves of the record the hour holds; delta and verdict exist only where it
#: holds both.
_ACCURACY_COLUMNS = (
    "spot_id",
    "time",
    "predicted",
    "observed",
    "coverage",
    "delta",
    "verdict",
)


@st.cache_data(ttl=1800, show_spinner=False)
def all_spots_accuracy(
    spot_ids: tuple[str, ...], predictions_json: str
) -> pd.DataFrame:
    """Per spot and hour, what the record holds: a prediction, an observation, or both.

    Reuses the per-spot timeline the ride-quality panel used to draw, so this
    introduces no call the console was not already making -- it makes it for
    every spot rather than only the focused one. Both layers are cached for
    half an hour, which is what keeps that widening affordable.

    Only an hour carrying BOTH halves can be graded, so delta and verdict are
    set there and left null everywhere else. The unpaired hours still ride
    along: "predicted and never measured" is exactly what the coverage band
    exists to show.
    """
    frames: list[pd.DataFrame] = []
    for spot_id in spot_ids:
        timeline = spot_quality_timeline(spot_id, predictions_json)
        if timeline.empty:
            continue
        wide = timeline.pivot_table(
            index="time", columns="series", values="quality_index", aggfunc="mean"
        )
        # A forward forecast and a logged past prediction are both predictions;
        # where an hour has each, the logged one wins, since it is what the
        # console actually said while the session could still be ridden.
        predicted = pd.Series(float("nan"), index=wide.index)
        for column in ("Forecast", "Predicted (past)"):
            if column in wide.columns:
                predicted = wide[column].combine_first(predicted)
        observed = (
            wide["Observed"]
            if "Observed" in wide.columns
            else pd.Series(float("nan"), index=wide.index)
        )
        frames.append(
            pd.DataFrame(
                {
                    "spot_id": spot_id,
                    "time": wide.index,
                    "predicted": predicted.to_numpy(),
                    "observed": observed.to_numpy(),
                }
            )
        )
    if not frames:
        return pd.DataFrame(columns=list(_ACCURACY_COLUMNS))
    out = pd.concat(frames, ignore_index=True)
    out = out[out[["predicted", "observed"]].notna().any(axis=1)].reset_index(drop=True)
    out["coverage"] = "both"
    out.loc[out["observed"].isna(), "coverage"] = "predicted"
    out.loc[out["predicted"].isna(), "coverage"] = "observed"
    out["delta"] = (out["predicted"] - out["observed"]).abs()
    out["verdict"] = out["delta"].map(
        lambda d: (
            None
            if pd.isna(d)
            else ("missed" if d > _ACCURACY_MISS_THRESHOLD else "matched")
        )
    )
    return out[list(_ACCURACY_COLUMNS)]


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
        # The hourly-cell rule (midpoint) keeps these cells on the wind plot's
        # night-band edges.
        cfg = spots_cfg.get(spot_id)
        frame["is_day"] = (
            is_daylight_hour(
                float(cfg["lat"]), float(cfg["lon"]), pd.DatetimeIndex(frame["hour"])
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

    # Danger is the other fact the quality level cannot carry. _score_row marks
    # an hour class 0 when it is too windy to ride, but quality_bucket sends
    # ANY index <= 0.5 to class 0, so a dangerous hour and a dead-calm one are
    # indistinguishable once the model has scored them. The cell therefore
    # reads the wind itself, against the same ceilings the labeling model uses.
    # Unknown wind stays False: absence of data is not safety, but a warning
    # with nothing behind it is worse than none, and the words below say which
    # case a cell is in.
    max_speed_kn, max_gust_kn = dangerous_kts()

    def _kn(column: str) -> pd.Series:
        if column not in grid.columns:
            return pd.Series(float("nan"), index=grid.index)
        return pd.to_numeric(grid[column], errors="coerce") / _KN_TO_KMH

    wind_kn, gust_kn = _kn("wind"), _kn("gust")
    grid["is_dangerous"] = (wind_kn > max_speed_kn) | (gust_kn > max_gust_kn)
    grid["safety"] = "Within the safe limits"
    grid.loc[wind_kn.isna() & gust_kn.isna(), "safety"] = "No wind reading"
    grid.loc[grid["is_dangerous"], "safety"] = (
        f"Too strong — over {max_speed_kn:.0f} kn or gusting over {max_gust_kn:.0f} kn"
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
    is_dangerous: bool = False,
) -> str:
    """Rounded metrics bubble for the selection row."""
    # The quality scale bottoms out at 1 here, so a dangerous hour would
    # otherwise read "1/5 (Too Light)" -- the exact opposite of the fact. The
    # level is still shown, because it is what the board painted, but the word
    # comes from the wind rather than from the floored level.
    label = "Too strong" if is_dangerous else quality_label(float(quality))
    rows = [_BUBBLE_ROW.format(label="Quality", value=f"{quality}/5 ({label})")]
    if is_dangerous:
        rows.append(_BUBBLE_ROW.format(label="Safety", value="Over the safe limit"))
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
            # D1: a dangerous hour reads "Too strong", never a quality label.
            bool(row.get("is_dangerous", False)),
        ),
        unsafe_allow_html=True,
    )


def _dial_summary(wind: float, gust: float | None, direction: float) -> str:
    """One line of wind for a dial's hover bubble: speed, gust and bearing."""
    gusting = "" if gust is None or pd.isna(gust) else f", gusting {gust:.0f}"
    return f"{wind:.0f} km/h{gusting}, {_compass(direction)} ({direction:.0f}°)"


def _dial_tile_html(name: str, dial_svg: str, selected: bool, summary: str = "") -> str:
    """One tile of the comparison grid: a compact dial with the spot's name.

    The selected spot wears the reading-orange border and the accent-text name;
    the rest keep a transparent border so every tile holds the same footprint.
    The summary rides on the tile's title, which is the only hover bubble a
    block of drawn HTML can raise without a component of its own.
    """
    pal = active()
    border = pal.reading if selected else "transparent"
    name_style = (
        f"color:{pal.accent_text};font-weight:700"
        if selected
        else "color:var(--muted);font-weight:600"
    )
    hover = f"{name} — {summary}" if summary else name
    return (
        f'<div title="{hover}" style="border:2px solid {border};border-radius:12px;'
        'padding:0.25rem 0.1rem 0.1rem;margin-bottom:0.3rem">'
        f"{dial_svg}"
        f'<div style="text-align:center;font-family:Manrope,sans-serif;'
        f'font-size:0.72rem;{name_style}">{name}</div></div>'
    )


def _focus_spot(spot_id: str) -> None:
    """Move the console's focus to a spot picked in the comparison grid.

    Mirrors the heatmap click: the console renders before the switcher and the
    map are instantiated later in the same script run, so writing the state
    here is legal, but the map is its own fragment and only an app-scope rerun
    reaches it. heat_spot_applied is deliberately left alone -- it mirrors the
    board's last applied click, which the chart re-reports on every rerun, so
    moving it here would set that stale selection fighting this pick.
    """
    if st.session_state.get("rider_focus_spot") == spot_id:
        return
    st.session_state["rider_focus_spot"] = spot_id
    st.rerun(scope="app")


def _render_dial_grid(
    spot_ids: list[str],
    selected_spot_id: str | None,
    hour: pd.Timestamp,
    min_kts: float,
) -> None:
    """Wind dials for every ranked spot at the selected hour, beside the board.

    All spots at one instant, so the selected spot's wind reads against its
    alternatives; the highlight marks which one the details below describe.
    Each tile carries a button, since a page cannot hear a click on an SVG it
    drew itself, and its own wind summary as a hover bubble.
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
                is_daylight_hour(
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
            summary = _dial_summary(wind, gust, direction)
            picked = spot_id == selected_spot_id
            st.markdown(
                _dial_tile_html(cfg["name"], svg, picked, summary),
                unsafe_allow_html=True,
            )
            if st.button(
                "Select",
                key=f"dial_pick_{spot_id}",
                help=f"{cfg['name']} — {summary}",
                disabled=picked,
            ):
                _focus_spot(spot_id)
    st.caption(
        "Each dial is that spot's wind at the selected hour: the dot's bearing "
        "is where the wind blows toward, its distance from the centre is speed "
        "(to 30 kn), and inside the teal band is a session. The orange frame "
        "marks the selected spot; hover a dial for its wind at this hour, or "
        "select another to switch the console to it."
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
    focus_spot: str | None
    now: pd.Timestamp | None
    cell: alt.Parameter
    hover_board: alt.Parameter
    hover_row: alt.Parameter
    hover_wind: alt.Parameter
    pin_time: alt.Parameter
    sun: pd.DataFrame = field(default_factory=pd.DataFrame)
    hour_verdicts: pd.DataFrame = field(default_factory=pd.DataFrame)
    hour_coverage: pd.DataFrame = field(default_factory=pd.DataFrame)
    focus_accuracy: pd.DataFrame = field(default_factory=pd.DataFrame)
    observed_selection: bool = False


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
    # The quality level cannot say "too much wind" -- it floors at 1, and the
    # danger class shares its number with a dead-calm hour. So the tooltip says
    # it in words, and says plainly when there is no wind reading to judge.
    if "safety" in heat_grid.columns:
        tooltip.append(alt.Tooltip("safety:N", title="Safety"))
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


_WIND_SERIES_TITLES = {
    "10m": "Wind 10 m (km/h)",
    "80m": "Wind 80 m (km/h)",
    "120m": "Wind 120 m (km/h)",
    "gusts": "Gusts 10 m (km/h)",
}


def _wind_hit_frame(panel: _Panel, frame: pd.DataFrame) -> pd.DataFrame:
    """The wind plot's hit target: one row per hour, carrying that hour's readings.

    The hover bubble reads this row, so it can name the day and the hour and
    print every series drawn at it rather than the bare timestamp it sits on.
    Everything joins on the UTC hour, since the spine runs in the panel's
    display timezone and the timeline in its own.
    """
    hits = panel.spine.assign(
        hour=_utc_hours(panel.spine["time"]),
        day=pd.DatetimeIndex(panel.spine["time"]).strftime("%a %d %b"),
        clock=pd.DatetimeIndex(panel.spine["time"]).strftime("%H:%M"),
    )
    wide = frame.pivot_table(
        index="time", columns="elevation", values="wind_speed", aggfunc="mean"
    )
    wide.index = _utc_hours(wide.index)
    hits = hits.merge(
        wide[~wide.index.duplicated()], left_on="hour", right_index=True, how="left"
    )
    # The console holds no measured WIND -- the plot's series are all forecast
    # -- so the observed half of an hour is its quality index, which is the one
    # measured number the record does carry.
    if not panel.focus_accuracy.empty:
        graded = panel.focus_accuracy.set_index(
            _utc_hours(panel.focus_accuracy["time"])
        )
        graded = graded[~graded.index.duplicated()]
        hits["predicted_quality"] = hits["hour"].map(graded["predicted"])
        hits["observed_quality"] = hits["hour"].map(graded["observed"])
    return hits.drop(columns="hour")


def _wind_tooltip(hits: pd.DataFrame) -> list[alt.Tooltip]:
    """Hover bubble for the wind plot: the day, the hour, and the readings.

    The quality rows only appear for an hour the record actually holds, so a
    measured hour shows the observed index beside the predicted one and an
    unmeasured one says nothing it cannot back up.
    """
    tooltip = [
        alt.Tooltip(field="day", type="nominal", title="Date"),
        alt.Tooltip(field="clock", type="nominal", title="Time"),
    ]
    tooltip += [
        alt.Tooltip(field=series, type="quantitative", title=title, format=".0f")
        for series, title in _WIND_SERIES_TITLES.items()
        if series in hits.columns
    ]
    tooltip += [
        alt.Tooltip(field=column, type="quantitative", title=title, format=".2f")
        for column, title in (
            ("predicted_quality", "Predicted quality (1-5)"),
            ("observed_quality", "Observed quality (1-5)"),
        )
        if column in hits.columns
    ]
    return tooltip


def _hour_verdicts(accuracy: pd.DataFrame) -> pd.DataFrame:
    """Per-hour accuracy, collapsed across spots, for the ruler's tint.

    The board carries one verdict per spot AND hour; the ruler has only the
    hour, so an hour reads as missed when any spot's forecast missed it. The
    counts ride along in the tooltip, which is where the per-spot detail that
    the collapse drops comes back.
    """
    graded = (
        accuracy[accuracy["verdict"].notna()]
        if "verdict" in accuracy.columns
        else accuracy
    )
    if graded.empty:
        return pd.DataFrame(
            columns=["time", "time_end", "missed", "pairs", "worst", "verdict"]
        )
    grouped = graded.groupby("time", as_index=False).agg(
        missed=("verdict", lambda v: int((v == "missed").sum())),
        pairs=("verdict", "size"),
        worst=("delta", "max"),
    )
    grouped["time_end"] = grouped["time"] + pd.Timedelta(hours=1)
    grouped["verdict"] = grouped["missed"].map(
        lambda n: "missed" if n > 0 else "matched"
    )
    return grouped


def _hour_coverage(accuracy: pd.DataFrame) -> pd.DataFrame:
    """Per hour, which halves of the record exist and how far apart they are.

    The board's rows are spots and this band's are hours, so an hour counts as
    predicted or observed as soon as any spot holds that half. Only the spots
    holding both can be compared, and their mean absolute quality-index gap is
    the hour's error; it lands in the same matched/missed classes the ruler's
    verdict tint uses, so one hour never reads two ways in one panel.
    """
    columns = [
        "time",
        "time_end",
        "coverage",
        "holds",
        "predicted",
        "observed",
        "paired",
        "error",
        "shade",
    ]
    if accuracy.empty:
        return pd.DataFrame(columns=columns)
    marked = accuracy.assign(
        has_predicted=accuracy["coverage"].isin(["predicted", "both"]),
        has_observed=accuracy["coverage"].isin(["observed", "both"]),
    )
    grouped = marked.groupby("time", as_index=False).agg(
        predicted=("has_predicted", "sum"),
        observed=("has_observed", "sum"),
        paired=("delta", "count"),
        error=("delta", "mean"),
    )
    grouped["time_end"] = grouped["time"] + pd.Timedelta(hours=1)
    both = (grouped["predicted"] > 0) & (grouped["observed"] > 0)
    grouped["holds"] = "Predicted only"
    grouped.loc[grouped["predicted"] == 0, "holds"] = "Observed only"
    grouped.loc[both, "holds"] = "Predicted and observed"
    grouped["coverage"] = "predicted"
    grouped.loc[grouped["predicted"] == 0, "coverage"] = "observed"
    grouped.loc[both, "coverage"] = grouped.loc[both, "error"].map(
        lambda e: "missed" if e > _ACCURACY_MISS_THRESHOLD else "matched"
    )
    # The class says whether the hour was called right, the shade by how much,
    # so a near miss and a wild one do not paint the same.
    grouped["shade"] = (
        0.4 + 0.6 * (grouped["error"] / _ACCURACY_MISS_THRESHOLD).clip(upper=1.0)
    ).fillna(0.4)
    return grouped[columns]


def _verdict_band(panel: _Panel) -> alt.Chart:
    """The hour's verdict as a tint on the time ruler.

    Colour and opacity move together: a matched hour is a quiet wash of the
    secondary ink, a missed one a solid danger tint, so the miss reads on a
    greyscale print too rather than resting on hue alone.
    """
    return (
        alt.Chart(panel.hour_verdicts)
        .mark_rect(clip=True)
        .encode(
            x=_panel_x(panel),
            x2=alt.X2("time_end:T"),
            color=alt.Color(
                "verdict:N",
                scale=alt.Scale(
                    domain=["matched", "missed"],
                    range=[panel.pal.ink_secondary, panel.pal.danger],
                ),
                legend=None,
            ),
            opacity=alt.condition(
                alt.datum.verdict == "missed", alt.value(0.85), alt.value(0.3)
            ),
            tooltip=[
                alt.Tooltip("time:T", title="Hour", format="%a %H:00"),
                alt.Tooltip("missed:Q", title="Spots missed", format=".0f"),
                alt.Tooltip("pairs:Q", title="Spots compared", format=".0f"),
                alt.Tooltip("worst:Q", title="Worst miss", format=".2f"),
            ],
        )
    )


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


def _selection_color(pal: Palette, observed: bool, *, text: bool = False) -> str:
    """What the selector wears, by what the selected hour actually holds.

    A predicted hour keeps the reading orange the console selects everything
    with. An observed one takes the neutral slate of the matched-verdict tint,
    so the crosshair says whether the numbers beside it are a forecast or a
    measurement instead of painting the two alike. That role clears the 4.5:1
    text floor in both modes, so the mark and its label can share it; the
    orange cannot, which is why the predicted label falls back to accent_text.
    """
    if observed:
        return pal.idle
    return pal.accent_text if text else pal.reading


def _utc_hours(times: Any) -> pd.DatetimeIndex:
    """The hour each timestamp falls in, in UTC.

    The panel runs in the display timezone and the timelines in UTC, so
    anything joining the two matches on this rather than on the timestamps.
    """
    index = pd.DatetimeIndex(times)
    index = index.tz_localize("UTC") if index.tz is None else index.tz_convert("UTC")
    return index.floor("h")


def _hour_is_observed(
    focus_accuracy: pd.DataFrame, pinned: pd.Timestamp | None
) -> bool:
    """Whether the pinned hour at the focused spot carries a measurement."""
    if pinned is None or focus_accuracy.empty:
        return False
    rows = focus_accuracy[_utc_hours(focus_accuracy["time"]) == _utc_hours([pinned])[0]]
    return bool(rows["observed"].notna().any())


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
    """The pinned time selector: a rule bisecting the pinned cell, in the colour
    of what that hour holds."""
    return (
        alt.Chart(_pin_frame(panel.pinned))
        .mark_rule(
            color=_selection_color(panel.pal, panel.observed_selection),
            strokeWidth=2,
            clip=True,
        )
        .encode(x=_panel_x(panel, "time_mid"))
    )


def _now_rule(panel: _Panel) -> alt.Chart:
    """The current instant, in the one saturated green every view marks it with.

    Drawn in both plots and on both rulers so "now" reads as a single line down
    the whole panel. It is also the boundary the board used to mark with a
    dashed grey rule: left of it the record is hindcast, right of it forecast.
    """
    return (
        alt.Chart(pd.DataFrame({"time": [panel.now]}))
        .mark_rule(color=panel.pal.band, strokeWidth=2, clip=True)
        .encode(x=_panel_x(panel))
    )


def _now_label(panel: _Panel) -> alt.Chart:
    """The word beside the NOW rule, so the green line is never read as a series."""
    return (
        alt.Chart(pd.DataFrame({"time": [panel.now], "label": ["NOW"]}))
        .mark_text(
            color=panel.pal.band,
            fontSize=10,
            fontWeight=700,
            align="left",
            baseline="middle",
            dx=4,
            clip=True,
        )
        .encode(x=_panel_x(panel), text="label:N")
    )


def _sun_marks(panel: _Panel) -> list[alt.Chart]:
    """Sunrise and sunset ticks on the ruler: one hue, told apart by dash.

    A colour encoding would need a scale of its own beside the verdict tint's,
    so each event is a layer at a constant colour instead. Sunrise is solid,
    sunset dashed, and both name themselves in the tooltip.
    """

    def mark(event: str, dash: list[int]) -> alt.Chart:
        return (
            alt.Chart(panel.sun[panel.sun["event"] == event])
            .mark_rule(color=panel.pal.sun, strokeWidth=1.5, strokeDash=dash, clip=True)
            .encode(x=_panel_x(panel), tooltip=[alt.Tooltip("label:N", title="Sun")])
        )

    return [mark("Sunrise", [1, 0]), mark("Sunset", [3, 2])]


def _focus_row_outline(panel: _Panel, rank_order: list[str]) -> alt.Chart:
    """The location half of the selector: the focused spot's row, outlined.

    The pinned hour draws a vertical rule, but a row is a band rather than an
    instant, so its counterpart is the band's own border: the cells inside keep
    their quality fill and stay readable under it.
    """
    return (
        alt.Chart(pd.DataFrame({"spot": [panel.focus_spot]}))
        .mark_rect(
            fillOpacity=0,
            stroke=_selection_color(panel.pal, panel.observed_selection),
            strokeWidth=2,
            clip=True,
        )
        .encode(y=alt.Y("spot:N", sort=rank_order))
    )


def _board_y_axis(
    pal: Palette, focus_spot: str | None, observed: bool = False
) -> alt.Axis:
    """The board's spot axis, printing the focused spot's name in the accent.

    A text-grade role rather than the mark colour for the same reason the ruler
    label wears one: an axis label is text on the page surface, so it has to
    clear the 4.5:1 floor the plain mark orange misses in light mode.
    """
    if focus_spot is None:
        return alt.Axis(orient="right", labelFontSize=13)
    test = f"datum.value === {json.dumps(focus_spot)}"
    return alt.Axis(
        orient="right",
        labelFontSize=13,
        labelColor={
            "condition": {
                "test": test,
                "value": _selection_color(pal, observed, text=True),
            },
            "value": pal.ink,
        },
        labelFontWeight={"condition": {"test": test, "value": 700}, "value": 400},
    )


def _ruler_view(panel: _Panel, orient: str) -> alt.Chart:
    """One ruler edge: the shared time axis, and what is worth reading off it.

    The axis carries the clock and the date; the strip itself carries the
    verdict tint, the sun marks, the NOW rule and the pinned hour's label. Only
    the axis-bearing layer may declare an axis and every sibling nulls its own,
    or vega-lite has two of them to merge across the layer.

    The pin label is accent_text rather than the reading orange the rule wears:
    it is text on the page surface, so it has to clear the 4.5:1 floor, which
    the plain mark orange does not.
    """
    axis = _ruler_axis(orient, panel.domain_start, panel.domain_end)
    layers = [
        alt.Chart(panel.spine)
        .mark_rule(opacity=0)
        .encode(x=alt.X("time:T", axis=axis, scale=panel.x_scale))
    ]
    if not panel.hour_verdicts.empty:
        layers.append(_verdict_band(panel))
    day = _day_label_frame(panel.domain_start)
    if not day.empty:
        layers.append(
            alt.Chart(day)
            .mark_text(
                color=panel.pal.ink_secondary,
                fontSize=10,
                align="left",
                baseline="middle",
                dx=3,
                clip=True,
            )
            .encode(x=_panel_x(panel), text="label:N")
        )
    layers.extend(_sun_marks(panel))
    if panel.now is not None:
        layers.extend([_now_rule(panel), _now_label(panel)])
    if panel.pinned is not None:
        pin = _pin_frame(panel.pinned)
        layers.append(
            alt.Chart(pin)
            .mark_rule(
                color=_selection_color(panel.pal, panel.observed_selection),
                strokeWidth=2,
                clip=True,
            )
            .encode(x=_panel_x(panel, "time_mid"))
        )
        layers.append(
            alt.Chart(pin)
            # No font family: the ruler's own labels take the chart default, and
            # a family the renderer does not have drops the glyphs silently.
            .mark_text(
                color=_selection_color(panel.pal, panel.observed_selection, text=True),
                fontSize=11,
                fontWeight=700,
                align="left",
                baseline="middle",
                dx=5,
            )
            .encode(x=_panel_x(panel, "time_mid"), text="label:N")
        )
    return alt.layer(*layers).properties(
        height=_RULER_HEIGHT_PX, width=_PANEL_PLOT_WIDTH
    )


def _board_view(
    panel: _Panel,
    heat_grid: pd.DataFrame,
    rank_order: list[str],
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
                axis=_board_y_axis(pal, panel.focus_spot, panel.observed_selection),
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

    # Dangerous hours, painted over their own cell. The fill below cannot carry
    # this: a conditional encoding falls back to ONE constant, which night
    # already claims, and the ramp floors these hours at level 1 -- the same
    # bare surface a dead-calm hour gets. Drawn as its own layer so the danger
    # colour is exact rather than a step on the quality ramp. It repeats the
    # tooltip because the top mark is the one that answers the pointer.
    if "is_dangerous" in heat_grid.columns and bool(heat_grid["is_dangerous"].any()):
        layers.append(
            alt.Chart(heat_grid)
            .mark_rect()
            .transform_filter("datum.is_dangerous")
            .encode(
                x=_panel_x(panel),
                x2="time_end:T",
                y=alt.Y("spot:N", title=None, sort=rank_order, axis=None),
                color=alt.value(pal.danger),
                tooltip=_heat_tooltip(heat_grid),
            )
        )

    # Where the record stops being hindcast and starts being forecast, in the
    # green the whole panel marks the present with.
    if panel.now is not None:
        layers.append(_now_rule(panel))

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
    # The selection crosshair: the focused spot's row crossing the pinned hour,
    # both in the same reading orange.
    if panel.focus_spot in rank_order:
        layers.append(_focus_row_outline(panel, rank_order))
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


def _coverage_view(panel: _Panel) -> alt.LayerChart:
    """The strip between the plots: what the record holds for each hour.

    Colour separates an hour the console only predicted from one only measured,
    and where both exist it takes the ruler's own matched/missed verdict; the
    shade then deepens with the mean absolute quality gap, so a near miss and a
    wild one do not paint the same. The NOW rule crosses it like every other
    view, which is what keeps the strip reading as part of the panel rather
    than as a legend stuck between two plots.
    """
    pal = panel.pal
    layers = [
        alt.Chart(panel.hour_coverage)
        .mark_rect(clip=True)
        .encode(
            x=_panel_x(panel),
            x2=alt.X2("time_end:T"),
            color=alt.Color(
                "coverage:N",
                scale=alt.Scale(
                    domain=["predicted", "observed", "matched", "missed"],
                    range=[pal.ink_muted, pal.night, pal.ink_secondary, pal.danger],
                ),
                legend=None,
            ),
            opacity=alt.Opacity(
                "shade:Q",
                scale=alt.Scale(domain=[0, 1], range=[0, 1]),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip("time:T", title="Hour", format="%a %d %b %H:00"),
                alt.Tooltip("holds:N", title="Record"),
                alt.Tooltip("predicted:Q", title="Spots predicted", format=".0f"),
                alt.Tooltip("observed:Q", title="Spots observed", format=".0f"),
                alt.Tooltip("error:Q", title="Quality error", format=".2f"),
            ],
        )
    ]
    if panel.now is not None:
        layers.append(_now_rule(panel))
    return alt.layer(*layers).properties(
        height=_COVERAGE_HEIGHT_PX, width=_PANEL_PLOT_WIDTH
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
    # A sample at H:00 borders the cells [H-1, H) and [H, H+1); it draws at
    # full strength when either neighbour is a daylight cell, so the bright
    # line runs edge-to-edge of the day region and meets the night wash
    # exactly where the heatmap's night cells begin.
    hours = pd.DatetimeIndex(timeline_frame["time"]).floor("h")
    cell_day = is_daylight_hour(spot_lat, spot_lon, hours).to_numpy()
    prev_day = is_daylight_hour(
        spot_lat, spot_lon, hours - pd.Timedelta(hours=1)
    ).to_numpy()
    frame = timeline_frame.assign(
        is_day=cell_day | prev_day,
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
    # The line is a light green and its label the text-grade green beside it:
    # the label is text on the page surface and has to clear the 4.5:1 floor,
    # which the ramp's light end does not.
    threshold = (
        alt.Chart(pd.DataFrame({"y": [threshold_kmh]}))
        .mark_rule(color=_light_green(pal), strokeDash=[4, 4], strokeWidth=2)
        .encode(y="y:Q")
    )
    threshold_label = (
        alt.Chart(
            pd.DataFrame(
                {"y": [threshold_kmh], "label": [f"{int(min_kts)} kn rideable"]}
            )
        )
        .mark_text(
            align="left", baseline="bottom", dx=6, dy=-3, color=pal.ok, fontSize=10
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
    # still pins a time. It is also the top mark, so it is the one that answers
    # the pointer, which is why the hour's readings ride on it. A rect on a
    # continuous x must declare x2.
    hit_frame = _wind_hit_frame(panel, frame)
    hits = (
        alt.Chart(hit_frame)
        .mark_rect(opacity=0)
        .encode(
            x=_panel_x(panel),
            x2="time_end:T",
            tooltip=_wind_tooltip(hit_frame),
        )
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
        *([_now_rule(panel)] if panel.now is not None else []),
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
    focus_spot: str | None = None,
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
    focus_accuracy = (
        accuracy[accuracy["spot"] == focus_spot]
        if focus_spot is not None and not accuracy.empty
        else pd.DataFrame(columns=list(_ACCURACY_COLUMNS))
    )
    panel = _Panel(
        spine=_time_spine(domain_start, domain_end),
        x_scale=alt.Scale(domain=domain, nice=False),
        domain_start=domain_start,
        domain_end=domain_end,
        pal=pal,
        pinned=pinned,
        focus_spot=focus_spot,
        now=now if domain_start <= now <= domain_end else None,
        sun=_sun_frame(domain_start, domain_end, spot_lat, spot_lon),
        hour_verdicts=_hour_verdicts(accuracy),
        hour_coverage=_hour_coverage(accuracy),
        focus_accuracy=focus_accuracy,
        observed_selection=_hour_is_observed(focus_accuracy, pinned),
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
        views.append(_board_view(panel, heat_grid, rank_order))
        modes.append("cell")
    if not panel.hour_coverage.empty:
        views.append(_coverage_view(panel))
    if not timeline_frame.empty:
        views.append(_wind_view(panel, timeline_frame, spot_lat, spot_lon, min_kts))
        modes.append("pin_time")
    views.append(_ruler_view(panel, "bottom"))

    return (
        alt.vconcat(*views, spacing=_PANEL_SPACING_PX, bounds="flush")
        .properties(
            background="transparent",
            # The y axes sit on the right, so the plot's left edge has no
            # gutter: a midnight ruler label near that edge center-anchors past
            # it and clips. The left padding buys the half-label of room. Top
            # and bottom hold the two rulers' axis bands, which the flush
            # layout leaves out of the view boxes (a padding OBJECT zeroes any
            # side left unspecified, hence all four).
            padding={
                "left": 26,
                "top": _RULER_AXIS_BAND_PX,
                "right": 6,
                "bottom": _RULER_AXIS_BAND_PX,
            },
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
                # The ruler's tint and the coverage strip are rects spanning
                # [H, H+1), so an hour has to stay on its own cell edge: the
                # half-cell offset the board's old accuracy dots needed would
                # slide both of them half an hour off the columns they grade.
                time=accuracy["time"].dt.tz_convert(display_tz),
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
                # The board's rows are spot NAMES, so the focused spot has to
                # arrive in that form. The labelled "Name (id)" the switcher
                # prints matched no row, which left both halves of the location
                # selector -- the row outline and the accented axis label --
                # drawing nothing at all.
                focus_spot=spot_lookup[focus_spot_id]["name"],
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
                    "Click anywhere in the panel to pin a time. The selector "
                    "labels the pinned hour on both rulers and outlines the "
                    "focused spot's row, in orange where that hour is a "
                    "forecast and in slate where it is a measurement. Both "
                    "rulers carry the clock and the date, a green NOW rule, "
                    "and amber ticks at sunrise (solid) and sunset (dashed). "
                    "The strip between the plots says what the record holds "
                    "for each hour. The green band along the wind plot traces "
                    "solar elevation, scaled to the wind-speed axis."
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
                    hours = _hour_verdicts(accuracy)
                    missed = int((hours["verdict"] == "missed").sum())
                    st.caption(
                        f"The time ruler is tinted left of the dashed line, "
                        f"where past forecasts can be compared with a quality "
                        f"index recomputed from archive data, which lags about "
                        f"five days, so recent hours are provisional: a quiet "
                        f"tint means every spot was called within "
                        f"{_ACCURACY_MISS_THRESHOLD:.0f} quality band, a red "
                        f"one means at least one spot missed "
                        f"({missed} of {len(hours)} hours). Hover an hour for "
                        f"the count."
                    )

    st.divider()

    render_wind_map(ranked_spots, _minimum_rideable_kts(), pred_hours)
