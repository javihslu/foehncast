"""Regional wind map: per-spot dials showing wind against the ideal window."""

from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import pandas as pd
import streamlit as st

from foehncast.config import get_labeling_config, get_rider_config, get_spots
from foehncast.feature_pipeline.ingest import fetch_forecast

from _dial_tokens import (
    HALO,
    INK as _INK,
    LIGHT_WIND as _COLOR_LIGHT,
    NEAR as _COLOR_NEAR,
    RIDEABLE as _COLOR_RIDEABLE,
    WEDGE_FILL_ALPHA,
    WEDGE_OUTLINE_ALPHA,
    rgb_to_hex as _rgb_to_hex,
)

_KN_TO_KMH = 1.852
_FORECAST_HOURS = 48

_COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


# Dial geometry: the radial scale maps 0-30 kn onto the ground radius, so
# needle length reads as speed and rings sit at 10/20/30 kn. The ideal wedge
# mirrors the labeling config: direction within +-45 deg of the shore
# orientation (cosine alignment >= 0.7) and the perfect-storm speed band.
_DIAL_MAX_KN = 30.0
_DIAL_RADIUS_KM = 18.0
_IDEAL_HALF_ANGLE_DEG = 45.0


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


def _dial_radius_km(speed_kn: float) -> float:
    return _DIAL_RADIUS_KM * min(speed_kn, _DIAL_MAX_KN) / _DIAL_MAX_KN


def _arc(
    lat: float, lon: float, radius_km: float, start_deg: float, end_deg: float
) -> list[list[float]]:
    """Polyline points along a ground-circle arc, in [lon, lat] pairs."""
    n = max(2, int(abs(end_deg - start_deg) / 6.0) + 1)
    return [
        _destination(
            lat, lon, start_deg + (end_deg - start_deg) * i / (n - 1), radius_km
        )
        for i in range(n)
    ]


def _status(speed_kn: float, min_kts: float) -> tuple[list[int], str]:
    if speed_kn >= min_kts:
        return _COLOR_RIDEABLE, "Rideable"
    if speed_kn >= 0.7 * min_kts:
        return _COLOR_NEAR, "Almost"
    return _COLOR_LIGHT, "Too light"


def _dial_base_records(
    spots: list[dict[str, Any]], ideal_band_kn: tuple[float, float]
) -> dict[str, list[dict[str, Any]]]:
    """Static dial chrome per spot: rings, ideal wedge, cardinal ticks, labels."""
    rings: list[dict[str, Any]] = []
    wedges: list[dict[str, Any]] = []
    ticks: list[dict[str, Any]] = []
    norths: list[dict[str, Any]] = []
    names: list[dict[str, Any]] = []
    for spot in spots:
        lat, lon = float(spot["lat"]), float(spot["lon"])
        for kn in (10.0, 20.0, 30.0):
            rings.append({"path": _arc(lat, lon, _dial_radius_km(kn), 0.0, 360.0)})
        flow = (float(spot["shore_orientation_deg"]) + 180.0) % 360.0
        a0 = flow - _IDEAL_HALF_ANGLE_DEG
        a1 = flow + _IDEAL_HALF_ANGLE_DEG
        outer = _arc(lat, lon, _dial_radius_km(ideal_band_kn[1]), a0, a1)
        inner = _arc(lat, lon, _dial_radius_km(ideal_band_kn[0]), a1, a0)
        wedges.append({"polygon": outer + inner})
        for bearing in (0.0, 90.0, 180.0, 270.0):
            p0 = _destination(lat, lon, bearing, _DIAL_RADIUS_KM)
            p1 = _destination(lat, lon, bearing, _DIAL_RADIUS_KM * 1.09)
            ticks.append(
                {
                    "from_lon": p0[0],
                    "from_lat": p0[1],
                    "to_lon": p1[0],
                    "to_lat": p1[1],
                }
            )
        north = _destination(lat, lon, 0.0, _DIAL_RADIUS_KM * 1.13)
        norths.append({"lon": north[0], "lat": north[1], "label": "N"})
        name_pt = _destination(lat, lon, 0.0, _DIAL_RADIUS_KM * 1.30)
        names.append({"lon": name_pt[0], "lat": name_pt[1], "name": spot["name"]})
    return {
        "rings": rings,
        "wedges": wedges,
        "ticks": ticks,
        "norths": norths,
        "names": names,
    }


def _needle_records(
    spot: dict[str, Any], row: pd.Series, min_kts: float
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Anchor plus needle and gust-tick segments for one spot at one hour."""
    speed_kn = float(row["wind_speed_10m"]) / _KN_TO_KMH
    gusts_kn = float(row["wind_gusts_10m"]) / _KN_TO_KMH
    direction = float(row["wind_direction_10m"])
    color, status = _status(speed_kn, min_kts)

    lat, lon = float(spot["lat"]), float(spot["lon"])
    flow = (direction + 180.0) % 360.0
    shaft_km = _dial_radius_km(speed_kn)
    tip = _destination(lat, lon, flow, shaft_km)
    head_km = max(shaft_km * 0.22, 0.9)

    def _segment(start: list[float], end: list[float], width: float) -> dict[str, Any]:
        return {
            "from_lon": start[0],
            "from_lat": start[1],
            "to_lon": end[0],
            "to_lat": end[1],
            "color": color,
            "width": width,
        }

    segments = [
        _segment([lon, lat], tip, 3.0),
        _segment(tip, _destination(tip[1], tip[0], (flow + 152) % 360, head_km), 3.0),
        _segment(tip, _destination(tip[1], tip[0], (flow - 152) % 360, head_km), 3.0),
        _segment(
            _destination(lat, lon, flow - 6.0, _dial_radius_km(gusts_kn)),
            _destination(lat, lon, flow + 6.0, _dial_radius_km(gusts_kn)),
            2.0,
        ),
    ]
    label_pt = _destination(lat, lon, 180.0, _DIAL_RADIUS_KM * 1.32)
    anchor = {
        "lat": lat,
        "lon": lon,
        "label_lon": label_pt[0],
        "label_lat": label_pt[1],
        "speed_label": f"{speed_kn:.0f} kn",
        "tooltip": (
            f"{spot['name']}: {speed_kn:.0f} kn from {_compass(direction)}"
            f" ({direction:.0f} deg), gusts {gusts_kn:.0f} kn - {status}"
        ),
    }
    return anchor, segments


@st.cache_data(ttl=1800, show_spinner=False)
def _hourly_map_records(
    spot_ids: tuple[str, ...], min_kts: float
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """Needle and anchor records for every forecast hour, keyed by ISO time."""
    spots_cfg = {s["id"]: s for s in get_spots()}
    out: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for sid in spot_ids:
        frame = _spot_wind_frame(sid)
        for ts, row in frame.iterrows():
            bucket = out.setdefault(ts.isoformat(), {"anchors": [], "segments": []})
            anchor, segments = _needle_records(spots_cfg[sid], row, min_kts)
            bucket["anchors"].append(anchor)
            bucket["segments"].extend(segments)
    return out


@st.fragment
def _render_map_fragment(spot_ids: list[str], min_kts: float) -> None:
    """Slider plus deck; a fragment so hour changes re-render only the map."""
    import pydeck as pdk

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

    # Mirror of the last hour this fragment has broadcast. A drag only
    # reruns this fragment, so an actual change forces an app-scope rerun --
    # that is how the heatmap (in the console fragment) redraws its
    # highlight. setdefault avoids a spurious rerun on first load; the
    # comparison keeps this quiet once both sides agree on the hour.
    st.session_state.setdefault("wind_map_hour_seen", hour)
    if st.session_state["wind_map_hour_seen"] != hour:
        st.session_state["wind_map_hour_seen"] = hour
        st.rerun(scope="app")

    spots_cfg = {s["id"]: s for s in get_spots()}
    storm_band = get_labeling_config()["bands"]["perfect_storm"]
    base = _dial_base_records(
        [spots_cfg[sid] for sid in spot_ids],
        (float(storm_band["min_kts"]), float(storm_band["max_kts"])),
    )
    hourly = _hourly_map_records(tuple(spot_ids), min_kts)
    records = hourly.get(hour.isoformat(), {"anchors": [], "segments": []})
    anchors, segments = records["anchors"], records["segments"]

    rider = get_rider_config()
    home = [
        {
            "lat": float(rider["home_lat"]),
            "lon": float(rider["home_lon"]),
            "name": "Rider home",
            "tooltip": "Rider home",
        }
    ]

    lats = [a["lat"] for a in anchors] + [home[0]["lat"]]
    lons = [a["lon"] for a in anchors] + [home[0]["lon"]]

    # Light casing under every needle so it reads on the muted basemap and where
    # needles cross rings or each other; the status-colored needle draws on top.
    halo = [{**s, "color": [*HALO, 215], "width": s["width"] + 3.0} for s in segments]
    layers = [
        # Rings: recessive reference chrome. A faint light halo lifts them off
        # the muted basemap without letting the grid compete with the needles.
        pdk.Layer(
            "PathLayer",
            data=base["rings"],
            get_path="path",
            get_color=[*HALO, 110],
            get_width=90,
            width_min_pixels=2.5,
        ),
        pdk.Layer(
            "PathLayer",
            data=base["rings"],
            get_path="path",
            get_color=[*_INK, 55],
            get_width=60,
            width_min_pixels=1.3,
        ),
        # Ideal wedge: a readable teal wash plus a full-opacity teal edge so the
        # ideal window is obvious at a glance.
        pdk.Layer(
            "PolygonLayer",
            data=base["wedges"],
            get_polygon="polygon",
            get_fill_color=[*_COLOR_RIDEABLE, WEDGE_FILL_ALPHA],
            stroked=True,
            get_line_color=[*_COLOR_RIDEABLE, WEDGE_OUTLINE_ALPHA],
            get_line_width=80,
            line_width_min_pixels=2,
        ),
        # Cardinal ticks: light halo under a recessive ink tick.
        pdk.Layer(
            "LineLayer",
            data=base["ticks"],
            get_source_position="[from_lon, from_lat]",
            get_target_position="[to_lon, to_lat]",
            get_color=[*HALO, 150],
            get_width=3.5,
        ),
        pdk.Layer(
            "LineLayer",
            data=base["ticks"],
            get_source_position="[from_lon, from_lat]",
            get_target_position="[to_lon, to_lat]",
            get_color=[*_INK, 140],
            get_width=2.0,
        ),
    ]
    layers += [
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
            get_radius=1200,
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
            get_radius=2200,
            pickable=True,
            stroked=True,
            get_line_color=[*_INK, 255],
            line_width_min_pixels=1,
        )
    )
    layers.append(
        pdk.Layer(
            "TextLayer",
            data=base["names"] + home,
            get_position="[lon, lat]",
            get_text="name",
            get_size=14,
            get_color=[*_INK, 255],
            get_alignment_baseline="'bottom'",
        )
    )
    layers.append(
        pdk.Layer(
            "TextLayer",
            data=base["norths"],
            get_position="[lon, lat]",
            get_text="label",
            get_size=13,
            get_color=[*_INK, 255],
            font_weight="bold",
            # pydeck 0.9.2 forwards these deck.gl TextLayer props: a light
            # background pill keeps the cardinal "N" legible over any tone.
            background=True,
            get_background_color=[*HALO, 205],
            background_padding=[3, 2],
        )
    )
    layers.append(
        pdk.Layer(
            "TextLayer",
            data=anchors,
            get_position="[label_lon, label_lat]",
            get_text="speed_label",
            get_size=12,
            get_color=[*_INK, 255],
            get_alignment_baseline="'top'",
        )
    )

    view = pdk.ViewState(
        latitude=(min(lats) + max(lats)) / 2,
        longitude=(min(lons) + max(lons)) / 2,
        zoom=7.4,
        pitch=0,
    )
    deck = pdk.Deck(
        layers=layers,
        initial_view_state=view,
        map_style="light",
        tooltip={"text": "{tooltip}"},
    )
    st.pydeck_chart(deck, use_container_width=True, height=620)

    chip = (
        '<span style="display:inline-block;width:0.7rem;height:0.7rem;'
        'border-radius:2px;background:{};margin:0 0.3rem 0 0.9rem"></span>{}'
    )
    st.markdown(
        '<p style="color:#07252a;font-size:0.85rem;margin-top:0.2rem">'
        "Rings mark 10/20/30 kn; the teal wedge is the spot's ideal window "
        "(direction &plusmn;45&deg;, "
        f"{storm_band['min_kts']:.0f}&ndash;{storm_band['max_kts']:.0f} kn). "
        "Needles point downwind, length is speed, the short tick marks gusts."
        + chip.format(_rgb_to_hex(_COLOR_RIDEABLE), f"Rideable (&ge; {min_kts:.0f} kn)")
        + chip.format(_rgb_to_hex(_COLOR_NEAR), "Almost")
        + chip.format(_rgb_to_hex(_COLOR_LIGHT), "Too light")
        + "</p>",
        unsafe_allow_html=True,
    )


def render_wind_map(ranked_spots: list[dict[str, Any]], min_kts: float) -> None:
    """Render the regional wind map for the ranked spots."""
    try:
        import pydeck  # noqa: F401
    except ImportError:
        st.info("Install pydeck to see the regional wind map.")
        return

    spots_cfg = {s["id"]: s for s in get_spots()}
    spot_ids = [s["spot_id"] for s in ranked_spots if s["spot_id"] in spots_cfg]
    if not spot_ids:
        return
    _warm_wind_frames(spot_ids)
    _render_map_fragment(spot_ids, min_kts)
