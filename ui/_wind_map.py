"""Regional wind map: per-spot direction arrows sized and colored by speed."""

from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import pandas as pd
import streamlit as st

from foehncast.config import get_rider_config, get_spots
from foehncast.feature_pipeline.ingest import fetch_forecast

_KN_TO_KMH = 1.852
_FORECAST_HOURS = 48

_INK = [7, 37, 42]
_COLOR_RIDEABLE = [10, 163, 146]
_COLOR_NEAR = [255, 122, 38]
_COLOR_LIGHT = [139, 163, 163]

_COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


@st.cache_data(ttl=1800, show_spinner=False)
def _spot_wind_frame(spot_id: str) -> pd.DataFrame:
    """Hourly 10 m wind speed, direction, and gusts for one spot."""
    spot = next((s for s in get_spots() if s["id"] == spot_id), None)
    if spot is None:
        return pd.DataFrame()
    frame = fetch_forecast(spot["lat"], spot["lon"], forecast_hours=_FORECAST_HOURS)
    cols = ["wind_speed_10m", "wind_direction_10m", "wind_gusts_10m"]
    if frame.empty or any(c not in frame.columns for c in cols):
        return pd.DataFrame()
    out = frame[cols].copy()
    out.index = pd.to_datetime(out.index)
    return out


def _warm_wind_frames(spot_ids: list[str]) -> None:
    with ThreadPoolExecutor(max_workers=min(len(spot_ids), 6)) as pool:
        futures = [pool.submit(_spot_wind_frame, sid) for sid in spot_ids]
        for f in as_completed(futures):
            try:
                f.result()
            except Exception:
                pass


def _destination(lat: float, lon: float, bearing_deg: float, km: float) -> list[float]:
    """Coordinates reached from (lat, lon) along a bearing, in [lon, lat]."""
    rad = math.radians(bearing_deg)
    dlat = km * math.cos(rad) / 110.574
    dlon = km * math.sin(rad) / (111.320 * math.cos(math.radians(lat)))
    return [lon + dlon, lat + dlat]


def _compass(direction_deg: float) -> str:
    return _COMPASS[int(((direction_deg + 22.5) % 360) // 45)]


def _arrow_records(
    spot: dict[str, Any], row: pd.Series, min_kts: float
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Anchor record plus shaft/head segments for one spot at one hour."""
    speed_kn = float(row["wind_speed_10m"]) / _KN_TO_KMH
    gusts_kn = float(row["wind_gusts_10m"]) / _KN_TO_KMH
    direction = float(row["wind_direction_10m"])
    if speed_kn >= min_kts:
        color, status = _COLOR_RIDEABLE, "Rideable"
    elif speed_kn >= 0.7 * min_kts:
        color, status = _COLOR_NEAR, "Almost"
    else:
        color, status = _COLOR_LIGHT, "Too light"

    lat, lon = float(spot["lat"]), float(spot["lon"])
    flow = (direction + 180.0) % 360.0
    shaft_km = 10.0 + min(speed_kn, 30.0) * 0.5
    width = 2.5 + min(speed_kn, 30.0) * 0.12
    tip = _destination(lat, lon, flow, shaft_km)
    head_km = shaft_km * 0.3

    def _segment(start: list[float], end: list[float]) -> dict[str, Any]:
        return {
            "from_lon": start[0],
            "from_lat": start[1],
            "to_lon": end[0],
            "to_lat": end[1],
            "color": color,
            "width": width,
        }

    segments = [
        _segment([lon, lat], tip),
        _segment(tip, _destination(tip[1], tip[0], (flow + 152) % 360, head_km)),
        _segment(tip, _destination(tip[1], tip[0], (flow - 152) % 360, head_km)),
    ]
    anchor = {
        "lat": lat,
        "lon": lon,
        "name": spot["name"],
        "speed_label": f"{speed_kn:.0f} kn",
        "tooltip": (
            f"{spot['name']}: {speed_kn:.0f} kn from {_compass(direction)}"
            f" ({direction:.0f} deg), gusts {gusts_kn:.0f} kn - {status}"
        ),
    }
    return anchor, segments


def render_wind_map(ranked_spots: list[dict[str, Any]], min_kts: float) -> None:
    """Render the regional wind map for the ranked spots at a chosen hour."""
    try:
        import pydeck as pdk
    except ImportError:
        st.info("Install pydeck to see the regional wind map.")
        return

    spots_cfg = {s["id"]: s for s in get_spots()}
    spot_ids = [s["spot_id"] for s in ranked_spots if s["spot_id"] in spots_cfg]
    if not spot_ids:
        return
    _warm_wind_frames(spot_ids)

    frames = {sid: _spot_wind_frame(sid) for sid in spot_ids}
    times = next((f.index for f in frames.values() if not f.empty), None)
    if times is None:
        st.info("No forecast data available for the wind map right now.")
        return

    st.subheader("Regional wind — direction and strength")
    hour = st.select_slider(
        "Forecast hour",
        options=list(times),
        value=times[0],
        format_func=lambda t: t.strftime("%a %H:%M"),
        key="wind_map_hour",
    )

    anchors: list[dict[str, Any]] = []
    segments: list[dict[str, Any]] = []
    for sid in spot_ids:
        frame = frames[sid]
        if frame.empty or hour not in frame.index:
            continue
        anchor, segs = _arrow_records(spots_cfg[sid], frame.loc[hour], min_kts)
        anchors.append(anchor)
        segments.extend(segs)

    rider = get_rider_config()
    home = [
        {
            "lat": float(rider["home_lat"]),
            "lon": float(rider["home_lon"]),
            "name": "Rider home",
            "speed_label": "",
            "tooltip": "Rider home",
        }
    ]

    lats = [a["lat"] for a in anchors] + [home[0]["lat"]]
    lons = [a["lon"] for a in anchors] + [home[0]["lon"]]

    halo = [
        {**s, "color": [7, 37, 42, 60], "width": s["width"] + 2.5} for s in segments
    ]
    layers = [
        pdk.Layer(
            "LineLayer",
            data=data,
            get_source_position="[from_lon, from_lat]",
            get_target_position="[to_lon, to_lat]",
            get_color="color",
            get_width="width",
        )
        for data in (halo, segments)
    ]
    layers.append(
        pdk.Layer(
            "ScatterplotLayer",
            data=anchors,
            get_position="[lon, lat]",
            get_fill_color=[*_INK, 235],
            get_radius=1600,
            pickable=True,
            stroked=True,
            get_line_color=[252, 252, 251, 255],
            line_width_min_pixels=1,
        )
    )
    layers.append(
        pdk.Layer(
            "ScatterplotLayer",
            data=home,
            get_position="[lon, lat]",
            get_fill_color=[255, 122, 38, 240],
            get_radius=2600,
            pickable=True,
            stroked=True,
            get_line_color=[*_INK, 255],
            line_width_min_pixels=1,
        )
    )
    layers.append(
        pdk.Layer(
            "TextLayer",
            data=anchors + home,
            get_position="[lon, lat]",
            get_text="name",
            get_size=14,
            get_color=[*_INK, 255],
            get_alignment_baseline="'bottom'",
            get_pixel_offset=[0, -12],
        )
    )
    layers.append(
        pdk.Layer(
            "TextLayer",
            data=anchors,
            get_position="[lon, lat]",
            get_text="speed_label",
            get_size=12,
            get_color=[*_INK, 255],
            get_alignment_baseline="'top'",
            get_pixel_offset=[0, 14],
        )
    )

    view = pdk.ViewState(
        latitude=(min(lats) + max(lats)) / 2,
        longitude=(min(lons) + max(lons)) / 2,
        zoom=7,
        pitch=0,
    )
    deck = pdk.Deck(
        layers=layers,
        initial_view_state=view,
        map_style="light",
        tooltip={"text": "{tooltip}"},
    )
    st.pydeck_chart(deck, use_container_width=True)

    chip = (
        '<span style="display:inline-block;width:0.7rem;height:0.7rem;'
        'border-radius:2px;background:{};margin:0 0.3rem 0 0.9rem"></span>{}'
    )
    st.markdown(
        '<p style="color:#07252a;font-size:0.85rem;margin-top:0.2rem">'
        "Arrows point downwind; labels show 10 m wind in knots."
        + chip.format("#0aa392", f"Rideable (&ge; {min_kts:.0f} kn)")
        + chip.format("#ff7a26", "Almost")
        + chip.format("#8ba3a3", "Too light")
        + "</p>",
        unsafe_allow_html=True,
    )
