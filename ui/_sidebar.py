"""Sidebar rendering: freshness bar, ML panels, spot map."""

from __future__ import annotations

import time as _time

import streamlit as st

from foehncast.airflow_api import airflow_triggers_available, trigger_dag

from _gcp import in_cloud_runtime, trigger_pipeline
from _promql import prom_query_batch

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


_FRESHNESS_SOURCES: list[tuple[str, str, bool, str]] = [
    (
        "Features",
        "foehncast_feature_pipeline_summary_generated_timestamp_seconds",
        True,
        "feature_pipeline",
    ),
    (
        "Training",
        "foehncast_training_pipeline_summary_generated_timestamp_seconds",
        True,
        "training_pipeline",
    ),
    (
        "Inference",
        "max(foehncast_prediction_log_latest_prediction_timestamp_seconds)",
        False,
        "inference_pipeline",
    ),
]


@st.cache_data(ttl=30, show_spinner=False)
def airflow_triggers_ready() -> bool:
    """Cached Airflow reachability/auth probe, shared by the sidebar and System tab."""
    return airflow_triggers_available()


def _render_run_control(label: str, dag_id: str) -> None:
    """Compact popover with a single confirm button that triggers dag_id."""
    with st.popover("Run", use_container_width=True):
        st.caption(f"Trigger the {dag_id} DAG now.")
        if st.button("Confirm run", key=f"run_{dag_id}", use_container_width=True):
            result = trigger_dag(dag_id)
            if result.ok:
                st.toast(f"{label}: queued {result.dag_run_id}")
            else:
                st.toast(f"{label} trigger failed — {result.error}")


def _render_cloud_run_control() -> None:
    """Trigger the Cloud Workflows cascade (feature -> training -> inference)."""
    with st.popover("Run pipeline", use_container_width=True):
        st.caption("Trigger the Cloud Workflows cascade now.")
        if st.button("Confirm run", key="run_cascade", use_container_width=True):
            execution = trigger_pipeline()
            if execution:
                st.toast(f"Cascade queued — {execution.rsplit('/', 1)[-1]}")
            else:
                st.toast("Cascade trigger failed")


@st.fragment(run_every=30)
def render_freshness_bar() -> None:
    """Source-by-source circular indicators, auto-refreshed every 30 s."""
    cols = st.columns(len(_FRESHNESS_SOURCES))
    now = _time.time()
    exprs = [src[1] for src in _FRESHNESS_SOURCES]
    values = prom_query_batch(exprs)
    cloud = in_cloud_runtime()
    triggers_ok = False if cloud else airflow_triggers_ready()
    for col, (label, _expr, scheduled, dag_id), ts in zip(
        cols, _FRESHNESS_SOURCES, values
    ):
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
            if triggers_ok:
                _render_run_control(label, dag_id)
    if cloud:
        _render_cloud_run_control()


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
        if display.startswith("-") and not display.strip("-0.%"):
            display = display[1:]
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
