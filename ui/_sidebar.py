"""Sidebar rendering: freshness bar, ML panels, spot map."""

from __future__ import annotations

import time as _time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pandas as pd
import streamlit as st

from foehncast.config import get_rider_config, get_spots

from ui._promql import prom_query, prom_query_batch

_PREDICTION_CYCLE_SECONDS = 6 * 3600  # Airflow schedule: 0 */6 * * *


def fmt_delta(seconds: float) -> str:
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
    if scheduled:
        remaining = max(0.0, _PREDICTION_CYCLE_SECONDS - elapsed)
        pct = min(1.0, elapsed / _PREDICTION_CYCLE_SECONDS)
        overdue = elapsed > _PREDICTION_CYCLE_SECONDS

        if overdue:
            ring_color, center_text = "#ff6e6e", "overdue"
        elif pct > 0.75:
            ring_color, center_text = "#d1833d", fmt_delta(remaining)
        else:
            ring_color, center_text = "#0e6d6e", fmt_delta(remaining)
        degrees = pct * 360
        subtitle = f"{fmt_delta(elapsed)} ago"
    else:
        degrees = 360
        ring_color = "#5f6f7f"
        center_text = fmt_delta(elapsed)
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
def render_freshness_bar() -> None:
    """Source-by-source circular indicators, auto-refreshed every 30 s."""
    cols = st.columns(len(_FRESHNESS_SOURCES))
    now = _time.time()
    exprs = [src[1] for src in _FRESHNESS_SOURCES]
    with ThreadPoolExecutor(max_workers=len(exprs)) as pool:
        values = list(pool.map(prom_query, exprs))
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


def render_sidebar_ml_panels() -> None:
    """Champion model status card with PromQL metrics."""
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
    ) = prom_query_batch(_sidebar_exprs)

    verified = (eval_ok is not None and eval_ok >= 1) and (
        reg_ok is not None and reg_ok >= 1
    )
    ver_label = f"v{int(model_ver)}" if model_ver is not None else "—"
    if hindcast_n is not None and hindcast_n < 1:
        hindcast_acc = None
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


def render_spot_map(ranked_spots: list[dict[str, Any]]) -> None:
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
