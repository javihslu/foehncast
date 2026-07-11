"""System tab: pipeline rails, prediction health, drift breakdown."""

from __future__ import annotations

import time as _time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any

import streamlit as st

from foehncast.airflow_api import AirflowDagRun, AirflowDagRunsResult, list_dag_runs
from foehncast.env import env_value

from _promql import prom_query_batch, prom_query_vector
from _sidebar import airflow_triggers_ready, fmt_delta

# Dataset the panels report on: forecast in the cloud, train locally.
_DATASET = env_value("FOEHNCAST_UI_DATASET") or "forecast"
_DRIFT_COMPARISON = env_value("FOEHNCAST_UI_DRIFT_COMPARISON") or "train-vs-forecast"

_PIPELINE_RAILS: list[dict[str, Any]] = [
    {
        "key": "feature",
        "title": "Feature pipeline",
        "dag_id": "feature_pipeline",
        "success_metric": "foehncast_feature_pipeline_run_success",
        "summary_ts_metric": "foehncast_feature_pipeline_summary_generated_timestamp_seconds",
        "stages_query": (
            f'foehncast_feature_pipeline_stage_state{{dataset="{_DATASET}"}}'
        ),
        "stage_duration_query": (
            f'foehncast_feature_pipeline_stage_duration_seconds{{dataset="{_DATASET}"}}'
        ),
        "stage_order": ["fetch", "engineer", "validate", "store"],
        "metric_chips": [
            ("stored spots", "foehncast_feature_pipeline_stored_spot_count", "int"),
            ("drifted", "foehncast_feature_pipeline_drifted_spot_count", "int"),
            ("failed", "foehncast_feature_pipeline_failed_spot_count", "int"),
            (
                "dataset drift",
                "foehncast_feature_pipeline_dataset_drift_detected",
                "bool",
            ),
            ("ingest rows", "foehncast_feature_pipeline_spot_ingest_rows", "int"),
        ],
    },
    {
        "key": "training",
        "title": "Training pipeline",
        "dag_id": "training_pipeline",
        "success_metric": "foehncast_training_pipeline_run_success",
        "summary_ts_metric": "foehncast_training_pipeline_summary_generated_timestamp_seconds",
        "stages_query": (
            'foehncast_training_pipeline_stage_state{requested_stage="Production"}'
        ),
        "stage_duration_query": (
            'foehncast_training_pipeline_stage_duration_seconds{requested_stage="Production"}'
        ),
        "stage_order": ["train", "evaluate", "register"],
        "metric_chips": [
            ("rows", "foehncast_training_pipeline_row_count", "int"),
            ("features", "foehncast_training_pipeline_feature_count", "int"),
            ("R²", 'foehncast_training_pipeline_run_metric{metric_name="r2"}', "f2"),
            (
                "RMSE",
                'foehncast_training_pipeline_run_metric{metric_name="rmse"}',
                "f3",
            ),
            (
                "model",
                "foehncast_training_pipeline_registered_model_version",
                "version",
            ),
        ],
    },
    {
        "key": "inference",
        "title": "Inference pipeline",
        "dag_id": "inference_pipeline",
        "success_metric": None,
        "summary_ts_metric": (
            "max(foehncast_prediction_log_latest_prediction_timestamp_seconds)"
        ),
        "stages_query": None,
        "stage_duration_query": None,
        "stage_order": [],
        "metric_chips": [
            ("predictions", "foehncast_prediction_log_total_row_count", "int"),
            ("models", "foehncast_prediction_log_model_count", "int"),
            (
                "hindcast",
                "foehncast_hindcast_accuracy",
                "pct",
            ),
            (
                "confidence",
                'clamp_max(1 - max(foehncast_drift_metric{metric_name="share_of_drifted_columns"}), 1)',
                "pct",
            ),
        ],
    },
]


def _stage_index(rail: dict[str, Any]) -> dict[str, dict[str, float]]:
    """Return ``{stage_name: {state, duration}}`` for a rail."""
    out: dict[str, dict[str, float]] = {
        stage: {"state": float("nan"), "duration": float("nan")}
        for stage in rail["stage_order"]
    }
    if rail.get("stages_query"):
        for entry in prom_query_vector(rail["stages_query"]):
            stage = entry["labels"].get("stage")
            if stage in out:
                out[stage]["state"] = entry["value"]
    if rail.get("stage_duration_query"):
        for entry in prom_query_vector(rail["stage_duration_query"]):
            stage = entry["labels"].get("stage")
            if stage in out:
                out[stage]["duration"] = entry["value"]
    return out


def _stage_pill_html(name: str, state: float, duration: float) -> str:
    if state != state:  # NaN
        bg, fg, dot, label = "#eef3ee", "#3b5a5a", "#9aa5a5", "—"
    elif state >= 0.999:
        bg, fg, dot, label = "rgba(14, 138, 134, 0.14)", "#07252a", "#0e8a86", "ok"
    elif state <= -0.5:
        bg, fg, dot, label = "rgba(192, 57, 43, 0.10)", "#c0392b", "#c0392b", "fail"
    else:
        bg, fg, dot, label = "rgba(255, 122, 38, 0.14)", "#7a3f10", "#ff7a26", "running"
    dur_text = (
        f"{duration:.2f}s"
        if (duration == duration and duration < 60)
        else (f"{duration / 60:.1f}m" if duration == duration else "—")
    )
    return (
        f'<div style="display:flex;align-items:center;gap:8px;'
        f"padding:6px 12px;border-radius:999px;background:{bg};color:{fg};"
        f'font-family:Manrope,sans-serif;font-size:0.78rem;font-weight:600">'
        f'<span style="width:8px;height:8px;border-radius:50%;background:{dot}"></span>'
        f"<span>{name}</span>"
        f'<span style="color:#5f6f7f;font-weight:500;font-size:0.72rem">{label} · {dur_text}</span>'
        "</div>"
    )


def _format_chip(value: float | None, kind: str) -> str:
    if value is None:
        return "—"
    if kind == "int":
        return f"{int(value)}"
    if kind == "f2":
        return f"{value:.2f}"
    if kind == "f3":
        return f"{value:.3f}"
    if kind == "pct":
        return f"{value * 100:.0f} %"
    if kind == "version":
        return f"v{int(value)}"
    if kind == "bool":
        return "drift" if value >= 0.5 else "clean"
    return f"{value:g}"


def _status_pill_html(success: float | None, summary_ts: float | None) -> str:
    if success is None and summary_ts is None:
        bg, fg, text = "#eef3ee", "#3b5a5a", "no data"
    elif success is None:
        bg, fg, text = "rgba(14, 138, 134, 0.14)", "#07252a", "live"
    elif success >= 0.5:
        bg, fg, text = "rgba(14, 138, 134, 0.16)", "#0e8a86", "last run ok"
    else:
        bg, fg, text = "rgba(192, 57, 43, 0.12)", "#c0392b", "last run failed"
    age = (
        f"{fmt_delta(_time.time() - summary_ts)} ago"
        if (summary_ts is not None and summary_ts > 0)
        else "no summary yet"
    )
    return (
        f'<div style="display:flex;align-items:center;gap:10px;'
        'font-family:Manrope,sans-serif;font-size:0.78rem">'
        f'<span style="padding:3px 10px;border-radius:999px;background:{bg};'
        f'color:{fg};font-weight:700">{text}</span>'
        f'<span style="color:#5f6f7f">{age}</span>'
        "</div>"
    )


# State colors match the app's status usage: teal for success, muted grey for
# in-flight (queued/running), red for failure.
_RUN_STATE_COLOR = {
    "success": "#0aa392",
    "queued": "#5f6f7f",
    "running": "#5f6f7f",
    "failed": "#ff6e6e",
}


def _run_age(run: AirflowDagRun) -> str:
    """Relative age of a run from its run_after (or logical) date."""
    stamp = run.run_after or run.logical_date
    if not stamp:
        return "—"
    try:
        started = datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return "—"
    return f"{fmt_delta(_time.time() - started)} ago"


def _run_row_html(run: AirflowDagRun) -> str:
    color = _RUN_STATE_COLOR.get(run.state, "#5f6f7f")
    state = run.state or "unknown"
    rid = run.dag_run_id.replace("<", "&lt;").replace(">", "&gt;") or "—"
    return (
        '<div style="display:flex;align-items:center;gap:8px;padding:3px 0">'
        f'<span style="display:inline-flex;align-items:center;gap:5px;'
        f"padding:2px 9px;border-radius:999px;background:{color}1a;color:{color};"
        f'font-family:Manrope,sans-serif;font-size:0.63rem;font-weight:700;min-width:62px">'
        f'<span style="width:6px;height:6px;border-radius:50%;background:{color}"></span>'
        f"{state}</span>"
        f'<span style="flex:1;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;'
        f"font-size:0.66rem;color:#07252a;overflow:hidden;text-overflow:ellipsis;"
        f'white-space:nowrap">{rid}</span>'
        f'<span style="font-family:Manrope,sans-serif;font-size:0.66rem;color:#5f6f7f;'
        f'white-space:nowrap">{_run_age(run)}</span>'
        "</div>"
    )


def _render_recent_runs(result: AirflowDagRunsResult | None) -> None:
    """Render recent DAG runs, or one short caption when unavailable."""
    if result is None:
        st.caption("Airflow unreachable — run history unavailable.")
        return
    if result.error:
        st.caption(f"Run history unavailable — {result.error}.")
        return
    if not result.runs:
        st.caption("No recent runs recorded.")
        return
    rows_html = "".join(_run_row_html(run) for run in result.runs)
    st.markdown(
        '<div style="max-height:170px;overflow-y:auto;padding:10px 12px;'
        "background:rgba(7,37,42,0.03);border-radius:8px;"
        'border:1px solid rgba(7,37,42,0.08)">' + rows_html + "</div>",
        unsafe_allow_html=True,
    )


def _render_pipeline_rail(rail: dict[str, Any], prefetched: dict[str, Any]) -> None:
    """Render one pipeline as a horizontal rail."""
    success = prefetched["success"]
    summary_ts = prefetched["summary_ts"]

    header_cols = st.columns([0.55, 0.45])
    with header_cols[0]:
        st.markdown(
            f'<div style="font-family:Manrope,sans-serif;font-weight:800;'
            f'font-size:0.95rem;color:#07252a;letter-spacing:0.01em">{rail["title"]}</div>',
            unsafe_allow_html=True,
        )
    with header_cols[1]:
        st.markdown(_status_pill_html(success, summary_ts), unsafe_allow_html=True)

    body_cols = st.columns([0.55, 0.45], gap="medium")
    with body_cols[0]:
        if rail["stage_order"]:
            stages = prefetched["stages"]
            pills_html = "".join(
                _stage_pill_html(name, stages[name]["state"], stages[name]["duration"])
                for name in rail["stage_order"]
            )
            st.markdown(
                '<div style="display:flex;flex-wrap:wrap;gap:8px;padding:6px 0">'
                + pills_html
                + "</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div style="font-family:Manrope,sans-serif;font-size:0.78rem;'
                'color:#5f6f7f;padding:6px 0">no stage metrics — see runs →</div>',
                unsafe_allow_html=True,
            )
    with body_cols[1]:
        _render_recent_runs(prefetched["runs"])

    chip_parts: list[str] = []
    for (label, _expr, kind), value in zip(
        rail["metric_chips"], prefetched["chip_values"]
    ):
        display = _format_chip(value, kind)
        chip_parts.append(
            f'<div style="display:flex;flex-direction:column;align-items:flex-start;'
            "padding:6px 12px;background:rgba(7,37,42,0.04);border-radius:8px;"
            'min-width:90px">'
            f'<span style="font-family:Manrope,sans-serif;font-size:0.62rem;'
            "font-weight:700;letter-spacing:0.04em;text-transform:uppercase;"
            f'color:#5f6f7f">{label}</span>'
            f'<strong style="font-family:Newsreader,serif;font-size:1rem;color:#07252a">{display}</strong>'
            "</div>"
        )
    st.markdown(
        '<div style="display:flex;flex-wrap:wrap;gap:8px;padding-top:6px;padding-bottom:6px">'
        + "".join(chip_parts)
        + "</div>",
        unsafe_allow_html=True,
    )


def _render_prediction_health() -> None:
    st.markdown(
        '<div style="font-family:Manrope,sans-serif;font-weight:800;'
        'font-size:0.95rem;color:#07252a;letter-spacing:0.01em;padding-bottom:8px">'
        "Prediction Health</div>",
        unsafe_allow_html=True,
    )

    health_exprs = [
        "foehncast_prediction_log_total_row_count",
        "foehncast_prediction_log_model_count",
        "max(foehncast_prediction_log_latest_prediction_timestamp_seconds)",
        "foehncast_prediction_monitoring_execution_total",
        "foehncast_hindcast_accuracy",
        "foehncast_hindcast_validated_count",
    ]
    per_model_query = "foehncast_prediction_log_row_count"

    with ThreadPoolExecutor(max_workers=2) as pool:
        scalars_future = pool.submit(prom_query_batch, health_exprs)
        models_future = pool.submit(prom_query_vector, per_model_query)

    total_rows, model_count, last_pred_ts, exec_total, hindcast_acc, hindcast_n = (
        scalars_future.result()
    )
    model_results = models_future.result()

    now = _time.time()
    pred_age = (
        fmt_delta(now - last_pred_ts) if last_pred_ts is not None else "unavailable"
    )
    if last_pred_ts is None:
        fresh_color = "#5f6f7f"
    elif (now - last_pred_ts) < 3600:
        fresh_color = "#0e8a86"
    elif (now - last_pred_ts) < 6 * 3600:
        fresh_color = "#ff7a26"
    else:
        fresh_color = "#c0392b"

    chips = [
        ("Predictions", f"{int(total_rows)}" if total_rows is not None else "—"),
        ("Models seen", f"{int(model_count)}" if model_count is not None else "—"),
        (
            "Last prediction",
            f'<span style="color:{fresh_color}">{pred_age}</span>',
        ),
        (
            "Monitor runs",
            f"{int(exec_total)}" if exec_total is not None else "—",
        ),
        (
            "Hindcast",
            (
                f"{hindcast_acc * 100:.0f} % ({int(hindcast_n)} pairs)"
                if hindcast_acc is not None
                and hindcast_n is not None
                and hindcast_n >= 1
                else "—"
            ),
        ),
    ]
    chips_html = "".join(
        f'<div style="display:flex;flex-direction:column;align-items:flex-start;'
        "padding:6px 12px;background:rgba(7,37,42,0.04);border-radius:8px;"
        'min-width:100px">'
        f'<span style="font-family:Manrope,sans-serif;font-size:0.62rem;'
        "font-weight:700;letter-spacing:0.04em;text-transform:uppercase;"
        f'color:#5f6f7f">{label}</span>'
        f'<strong style="font-family:Newsreader,serif;font-size:1rem;color:#07252a">{value}</strong>'
        "</div>"
        for label, value in chips
    )
    st.markdown(
        '<div style="display:flex;flex-wrap:wrap;gap:8px;padding-bottom:10px">'
        + chips_html
        + "</div>",
        unsafe_allow_html=True,
    )

    if model_results:
        models_sorted = sorted(model_results, key=lambda x: x["value"], reverse=True)
        max_count = max(e["value"] for e in models_sorted) if models_sorted else 1
        bars_html: list[str] = []
        for entry in models_sorted:
            version = entry["labels"].get("model_version", "?")
            count = int(entry["value"])
            pct = (count / max_count) * 100 if max_count > 0 else 0
            bars_html.append(
                f'<div style="display:flex;align-items:center;gap:8px;padding:3px 0">'
                f'<span style="font-family:Manrope,sans-serif;font-size:0.72rem;'
                f'font-weight:600;min-width:50px;color:#07252a">v{version}</span>'
                f'<div style="flex:1;height:14px;background:rgba(7,37,42,0.06);'
                f'border-radius:7px;overflow:hidden">'
                f'<div style="width:{pct:.0f}%;height:100%;background:#0e8a86;'
                f'border-radius:7px"></div></div>'
                f'<span style="font-family:Manrope,sans-serif;font-size:0.68rem;'
                f'font-weight:700;min-width:40px;text-align:right;color:#07252a">'
                f"{count}</span></div>"
            )
        st.markdown(
            '<div style="padding:4px 0">'
            '<span style="font-family:Manrope,sans-serif;font-size:0.62rem;'
            "font-weight:700;letter-spacing:0.04em;text-transform:uppercase;"
            'color:#5f6f7f">predictions per model version</span>'
            + "".join(bars_html)
            + "</div>",
            unsafe_allow_html=True,
        )


def _render_drift_breakdown() -> None:
    st.markdown(
        '<div style="font-family:Manrope,sans-serif;font-weight:800;'
        'font-size:0.95rem;color:#07252a;letter-spacing:0.01em;padding-bottom:8px">'
        "Data Drift Breakdown</div>",
        unsafe_allow_html=True,
    )

    # Share of drifted columns per spot (0 stable, 1 fully drifted). The raw
    # drift_score is a p-value where high means stable, so it does not suit
    # a red-is-bad bar.
    spot_query = (
        f"avg by (dataset_name) (foehncast_drift_metric"
        f'{{metric_name="share_of_drifted_columns",dataset_version="{_DRIFT_COMPARISON}"}})'
    )
    column_query = (
        f"sum by (column_name) (foehncast_drift_metric"
        f'{{metric_name="drift_detected",dataset_version="{_DRIFT_COMPARISON}"}})'
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        spot_future = pool.submit(prom_query_vector, spot_query)
        column_future = pool.submit(prom_query_vector, column_query)
    spot_results = spot_future.result()
    column_results = column_future.result()

    if not spot_results and not column_results:
        st.caption("No drift data available yet.")
        return

    if spot_results:
        spots_sorted = sorted(spot_results, key=lambda x: x["value"], reverse=True)
        bars_html: list[str] = []
        for entry in spots_sorted:
            name = entry["labels"].get("dataset_name", "?")
            score = entry["value"]
            if score < 0.3:
                bar_color = "#0e8a86"
            elif score < 0.7:
                bar_color = "#ff7a26"
            else:
                bar_color = "#c0392b"
            pct = min(score * 100, 100)
            bars_html.append(
                f'<div style="display:flex;align-items:center;gap:8px;padding:3px 0">'
                f'<span style="font-family:Manrope,sans-serif;font-size:0.72rem;'
                f'font-weight:600;min-width:110px;color:#07252a">{name}</span>'
                f'<div style="flex:1;height:14px;background:rgba(7,37,42,0.06);'
                f'border-radius:7px;overflow:hidden">'
                f'<div style="width:{pct:.0f}%;height:100%;background:{bar_color};'
                f'border-radius:7px"></div></div>'
                f'<span style="font-family:Manrope,sans-serif;font-size:0.68rem;'
                f'font-weight:700;min-width:40px;text-align:right;color:{bar_color}">'
                f"{score:.2f}</span></div>"
            )
        st.markdown(
            '<div style="padding:8px 0">' + "".join(bars_html) + "</div>",
            unsafe_allow_html=True,
        )

    if column_results:
        drifted = [e for e in column_results if e["value"] > 0]
        if drifted:
            drifted_sorted = sorted(drifted, key=lambda x: x["value"], reverse=True)[:8]
            chips_html: list[str] = []
            for entry in drifted_sorted:
                col_name = entry["labels"].get("column_name", "?")
                count = int(entry["value"])
                chips_html.append(
                    f'<span style="display:inline-block;padding:3px 10px;'
                    f"margin:2px 4px 2px 0;border-radius:12px;font-family:Manrope,sans-serif;"
                    f"font-size:0.68rem;font-weight:600;background:rgba(192,57,43,0.08);"
                    f'color:#c0392b">{col_name} ({count})</span>'
                )
            st.markdown(
                '<div style="padding:4px 0">'
                '<span style="font-family:Manrope,sans-serif;font-size:0.62rem;'
                "font-weight:700;letter-spacing:0.04em;text-transform:uppercase;"
                'color:#5f6f7f">drifted features</span><br/>'
                + "".join(chips_html)
                + "</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div style="font-family:Manrope,sans-serif;font-size:0.78rem;'
                'color:#0e8a86;padding:4px 0">✓ No drifted features detected</div>',
                unsafe_allow_html=True,
            )


def _render_pipelines_panel() -> None:
    """System tab body: three pipeline rails with recent Airflow run history."""
    # Per-pipeline Run controls live in the sidebar (local Airflow REST). Gate
    # the run-history fetches on the same cached probe so a down server costs
    # one short caption per rail, not three blocked auth round-trips.
    airflow_ok = airflow_triggers_ready()
    st.caption("Per-pipeline Run controls live in the sidebar (local Airflow).")

    # Pre-fetch ALL scalar metrics for all rails in one parallel batch.
    all_scalar_exprs: list[str] = []
    expr_map: list[tuple[int, str]] = []
    for rail_idx, rail in enumerate(_PIPELINE_RAILS):
        if rail.get("success_metric"):
            all_scalar_exprs.append(rail["success_metric"])
            expr_map.append((rail_idx, "success"))
        if rail.get("summary_ts_metric"):
            all_scalar_exprs.append(rail["summary_ts_metric"])
            expr_map.append((rail_idx, "summary"))
        for chip_idx, (_label, expr, _kind) in enumerate(rail["metric_chips"]):
            all_scalar_exprs.append(expr)
            expr_map.append((rail_idx, f"chip_{chip_idx}"))

    with ThreadPoolExecutor(max_workers=12) as pool:
        scalar_future = pool.submit(prom_query_batch, all_scalar_exprs)
        stage_futures = {
            idx: pool.submit(_stage_index, rail)
            for idx, rail in enumerate(_PIPELINE_RAILS)
            if rail["stage_order"]
        }
        run_futures = (
            {
                idx: pool.submit(list_dag_runs, rail["dag_id"], limit=5)
                for idx, rail in enumerate(_PIPELINE_RAILS)
            }
            if airflow_ok
            else {}
        )
        batch_results = scalar_future.result() if all_scalar_exprs else []

    rail_data: list[dict[str, Any]] = [
        {
            "success": None,
            "summary_ts": None,
            "chip_values": [],
            "stages": None,
            "runs": None,
        }
        for _ in _PIPELINE_RAILS
    ]
    for (rail_idx, key), value in zip(expr_map, batch_results):
        if key == "success":
            rail_data[rail_idx]["success"] = value
        elif key == "summary":
            rail_data[rail_idx]["summary_ts"] = value
        elif key.startswith("chip_"):
            rail_data[rail_idx]["chip_values"].append(value)
    for idx, future in stage_futures.items():
        rail_data[idx]["stages"] = future.result()
    for idx, future in run_futures.items():
        rail_data[idx]["runs"] = future.result()

    for index, rail in enumerate(_PIPELINE_RAILS):
        if index > 0:
            st.markdown(
                '<hr style="border:none;border-top:1px solid rgba(7,37,42,0.10);'
                'margin:14px 0">',
                unsafe_allow_html=True,
            )
        _render_pipeline_rail(rail, rail_data[index])


@st.fragment
def render_system_tab() -> None:
    """System tab: pipelines panel, prediction health, and drift breakdown.

    Rendered eagerly so the cached PromQL metrics are warm in the background
    by the time the rider opens this tab. Cached queries (15-30s TTL) keep
    repeat renders cheap.
    """
    _render_pipelines_panel()
    st.markdown(
        '<hr style="border:none;border-top:1px solid rgba(7,37,42,0.10);'
        'margin:18px 0">',
        unsafe_allow_html=True,
    )
    _render_drift_breakdown()
    st.markdown(
        '<hr style="border:none;border-top:1px solid rgba(7,37,42,0.10);'
        'margin:18px 0">',
        unsafe_allow_html=True,
    )
    _render_prediction_health()
