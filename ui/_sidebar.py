"""Sidebar rendering: freshness bar, ML panels, spot map."""

from __future__ import annotations

import time as _time

import streamlit as st

from _control import (
    ControlRuns,
    control_capabilities,
    control_runs,
    trigger_pipeline_run,
)
from _promql import prom_query_batch

_PREDICTION_CYCLE_SECONDS = 6 * 3600  # Airflow schedule: 0 */6 * * *

# A pipeline reads busy while its most recent run is queued or running; a fresh
# trigger also flags it in session state for up to this long, bridging the gap
# before Airflow materializes the run.
_BUSY_STATES = frozenset({"queued", "running"})
_QUEUED_KEY = "fc_queued"
_QUEUED_FLAG_TTL = 120.0

# Ring status colors, validated by the dataviz palette script (--pairs all,
# surface #eaf3ef): chroma floor, CVD and normal-vision separation all pass.
# The sub-3:1 contrast WARN is carried by the visible age + state labels.
_RING_FRESH = "#0aa38d"
_RING_AGING = "#d1861f"
_RING_OVERDUE = "#a93226"
_RING_IDLE = "#5f6f7f"
_RING_TRACK = "#e0ddd4"

_RING_RADIUS = 30
_RING_CIRCUMFERENCE = 2 * 3.14159265 * _RING_RADIUS


def fmt_delta(seconds: float) -> str:
    """Format a duration in seconds to a short human-readable string."""
    s = abs(int(seconds))
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m"
    h, m = divmod(s, 3600)
    return f"{h}h {m // 60}m"


def _ring_svg(color: str, sweep: float) -> str:
    """68 px ring as an SVG arc; rounded caps avoid the conic-gradient notch."""
    if sweep < 0.995:
        arc_len = _RING_CIRCUMFERENCE * max(0.0, sweep)
        dash = f'stroke-dasharray="{arc_len:.1f} {_RING_CIRCUMFERENCE:.1f}" '
    else:
        dash = ""  # a full ring is an unbroken circle: no seam, no notch
    return (
        '<svg class="fc-ring" width="68" height="68" viewBox="0 0 68 68" '
        'style="position:absolute;left:0;top:0">'
        f'<circle cx="34" cy="34" r="{_RING_RADIUS}" fill="none" '
        f'stroke="{_RING_TRACK}" stroke-width="7"/>'
        f'<circle class="fc-ring-arc" cx="34" cy="34" r="{_RING_RADIUS}" '
        f'fill="none" stroke="{color}" stroke-width="7" stroke-linecap="round" '
        f'{dash}transform="rotate(-90 34 34)"/>'
        "</svg>"
    )


def _freshness_circle_html(
    label: str,
    elapsed: float,
    *,
    scheduled: bool,
    interactive: bool = False,
    busy: str | None = None,
) -> str:
    # One semantic everywhere: the center is the data's age. Cycle position
    # and health move to the ring sweep/color; the countdown to the subtitle.
    if scheduled:
        remaining = max(0.0, _PREDICTION_CYCLE_SECONDS - elapsed)
        pct = min(1.0, elapsed / _PREDICTION_CYCLE_SECONDS)
        overdue = elapsed > _PREDICTION_CYCLE_SECONDS

        if overdue:
            ring_color, subtitle = _RING_OVERDUE, "overdue"
        elif pct > 0.75:
            ring_color, subtitle = _RING_AGING, f"next in {fmt_delta(remaining)}"
        else:
            ring_color, subtitle = _RING_FRESH, f"next in {fmt_delta(remaining)}"
        ring = _ring_svg(ring_color, 1.0 if overdue else pct)
    else:
        # On demand: a continuous idle-colored ring (distinct color still reads
        # "unscheduled"); no dashes, so the ring matches the scheduled dials.
        ring = _ring_svg(_RING_IDLE, 1.0)
        subtitle = "on demand"
    # A busy pipeline reads inactive: the subtitle reports the run state and the
    # wrapper dims via CSS, while the center still shows the data's age.
    if busy:
        subtitle = busy
    center_text = fmt_delta(elapsed)
    # Interactive dials double as buttons: the age swaps to a Run label on hover
    # (CSS, scoped to the .st-key-dialwrap_ wrapper), so stack both spans.
    if interactive:
        center = (
            f'<span class="fc-age">{center_text}</span><span class="fc-run">Run</span>'
        )
    else:
        center = center_text

    wrap = ' class="fc-busy"' if busy else ""
    return f"""
    <div{wrap} style="display:flex;flex-direction:column;align-items:center;gap:2px">
      <div style="
        position:relative;width:68px;height:68px;
        display:flex;align-items:center;justify-content:center;
      ">
        {ring}
        <div class="fc-disc" style="
          width:52px;height:52px;border-radius:50%;
          background:#faf6ee;position:relative;
          display:flex;align-items:center;justify-content:center;
          font-family:Manrope,sans-serif;font-weight:700;
          font-size:0.72rem;color:#17324d;
        ">{center}</div>
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
        "feature",
    ),
    (
        "Training",
        "foehncast_training_pipeline_summary_generated_timestamp_seconds",
        True,
        "training",
    ),
    (
        "Inference",
        "max(foehncast_prediction_log_latest_prediction_timestamp_seconds)",
        False,
        "inference",
    ),
]


@st.cache_data(ttl=30, show_spinner=False)
def pipeline_capabilities() -> list[str]:
    """Cached control-plane capabilities probe, shared across reruns."""
    return control_capabilities() or []


def _latest_states(result: ControlRuns) -> dict[str, str]:
    """Most-recent run state per pipeline from newest-first runs; {} on error."""
    if result.error:
        return {}
    states: dict[str, str] = {}
    for run in result.runs:
        pipeline = run.get("pipeline")
        if pipeline and pipeline not in states:
            states[pipeline] = str(run.get("state", ""))
    return states


@st.cache_data(ttl=30, show_spinner=False)
def pipeline_run_states() -> dict[str, str]:
    """Cached most-recent run state per pipeline, polled at the fragment cadence."""
    return _latest_states(control_runs())


def _queued_flags() -> dict[str, float]:
    """Session-persisted pipeline -> trigger-time map, created on first use."""
    flags = st.session_state.get(_QUEUED_KEY)
    if flags is None:
        flags = {}
        st.session_state[_QUEUED_KEY] = flags
    return flags


def _mark_queued(*pipelines: str) -> None:
    """Flag pipelines busy after a successful trigger and force a prompt re-poll."""
    flags = _queued_flags()
    stamp = _time.time()
    for pipeline in pipelines:
        flags[pipeline] = stamp
    pipeline_run_states.clear()


def _dial_busy(pipeline: str, run_states: dict[str, str], now: float) -> str | None:
    """Busy subtitle ('queued'/'running') for a dial, or None when idle.

    The poll wins: a most-recent run that is queued or running reports its own
    state and retires the session flag. Otherwise a fresh trigger flag reads
    'queued' until its TTL lapses, covering the gap before Airflow materializes
    the run.
    """
    flags = _queued_flags()
    poll_state = run_states.get(pipeline)
    if poll_state in _BUSY_STATES:
        flags.pop(pipeline, None)
        return poll_state
    flagged_at = flags.get(pipeline)
    if flagged_at is not None:
        if now - flagged_at < _QUEUED_FLAG_TTL:
            return "queued"
        del flags[pipeline]
    return None


def _render_dial_button(label: str, pipeline: str, *, busy: bool = False) -> None:
    """Transparent circular button overlaid on the dial; triggers on click."""
    if st.button(f"Run {label}", key=f"run_{pipeline}", disabled=busy):
        run_id, error = trigger_pipeline_run(pipeline)
        if run_id:
            _mark_queued(pipeline)
            st.toast(f"{label}: queued {run_id}")
            st.rerun(scope="fragment")
        else:
            st.toast(f"{label} trigger failed — {error}")


def _render_cascade_button(*, disabled: bool = False) -> None:
    """Full-width button that triggers the orchestrator's full cascade."""
    if st.button(
        "Run pipeline", key="run_cascade", use_container_width=True, disabled=disabled
    ):
        run_id, error = trigger_pipeline_run("cascade")
        if run_id:
            _mark_queued("feature", "training", "inference")
            st.toast(f"Cascade queued — {run_id.rsplit('/', 1)[-1]}")
            st.rerun(scope="fragment")
        else:
            st.toast(f"Cascade trigger failed — {error}")


def _render_freshness_bar() -> None:
    """Freshness dials; each capable pipeline's dial is a clickable button."""
    cols = st.columns(len(_FRESHNESS_SOURCES))
    now = _time.time()
    exprs = [src[1] for src in _FRESHNESS_SOURCES]
    values = prom_query_batch(exprs)
    capabilities = pipeline_capabilities()
    # No capable pipelines means no interactive dial, so skip the run-state poll.
    run_states = pipeline_run_states() if capabilities else {}
    busy = {
        pipeline: _dial_busy(pipeline, run_states, now)
        for _label, _expr, _scheduled, pipeline in _FRESHNESS_SOURCES
        if pipeline in capabilities
    }
    for col, (label, _expr, scheduled, pipeline), ts in zip(
        cols, _FRESHNESS_SOURCES, values
    ):
        with col:
            if ts is None:
                st.markdown(
                    f'<div style="text-align:center;opacity:0.4;'
                    f'font-size:0.75rem">{label}<br/>unavailable</div>',
                    unsafe_allow_html=True,
                )
                continue
            interactive = pipeline in capabilities
            busy_state = busy.get(pipeline)
            html = _freshness_circle_html(
                label,
                now - ts,
                scheduled=scheduled,
                interactive=interactive,
                busy=busy_state,
            )
            if interactive:
                with st.container(key=f"dialwrap_{pipeline}"):
                    st.markdown(html, unsafe_allow_html=True)
                    _render_dial_button(label, pipeline, busy=bool(busy_state))
            else:
                st.markdown(html, unsafe_allow_html=True)
    if "cascade" in capabilities:
        st.markdown(
            "<div style='margin-top:14px;padding-top:11px;"
            "border-top:1px solid rgba(7,37,42,0.08)'></div>",
            unsafe_allow_html=True,
        )
        _render_cascade_button(disabled=any(busy.values()))


@st.fragment(run_every=30)
def render_freshness_bar() -> None:
    """Source-by-source circular indicators, auto-refreshed every 30 s."""
    _render_freshness_bar()


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
        # Scoped to the per-spot vs-train comparisons: confidence means "how
        # much do current conditions resemble the training data". Prediction
        # drift legitimately spikes on promotion and must not zero this.
        'max(foehncast_drift_metric{metric_name="share_of_drifted_columns",'
        'dataset_version="train"})',
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
