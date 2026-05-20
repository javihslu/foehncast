"""Streamlit rider console for FoehnCast spot recommendations."""

from __future__ import annotations

from typing import Any

import streamlit as st

from foehncast.inference_pipeline.dashboard import (
    list_dashboard_spots,
    load_dashboard_data,
)

from _styles import inject_styles
from _sidebar import render_freshness_bar, render_sidebar_ml_panels
from _rider_console import profile_card, render_rider_console
from _system_tab import render_system_tab

st.set_page_config(
    page_title="FoehnCast Rider Console",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------------------
# Cached data loaders
# ---------------------------------------------------------------------------


@st.cache_data(show_spinner=False)
def _available_spots() -> list[dict[str, Any]]:
    return list_dashboard_spots()


@st.cache_data(ttl=1800, show_spinner=False)
def _live_dashboard_data(selected_spot_ids: tuple[str, ...]) -> dict[str, Any]:
    return load_dashboard_data(list(selected_spot_ids) if selected_spot_ids else None)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    inject_styles()

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
                profile_card(dashboard_data["rider_profile"]),
                unsafe_allow_html=True,
            )
            st.caption(
                "Drive-time ranking uses the rider home from config.yaml and live OSRM route estimates."
            )
        st.markdown('<div style="margin-top:1.2rem"></div>', unsafe_allow_html=True)
        render_freshness_bar()
        st.divider()
        render_sidebar_ml_panels()

    rider_tab, system_tab = st.tabs(["Rider Console", "System"])

    with rider_tab:
        if dashboard_error is not None:
            st.error(
                "Could not load the current forecast and model stack. Check MLflow, "
                "network access, and the configured serving model alias."
            )
            st.exception(dashboard_error)
        elif dashboard_data is not None:
            render_rider_console(dashboard_data, all_spot_ids, spot_lookup)

    with system_tab:
        render_system_tab()


main()
