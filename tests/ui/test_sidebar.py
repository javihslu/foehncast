"""Tests for the sidebar freshness dials: one age semantic, dial-as-button."""

from __future__ import annotations

import pathlib
import sys
import types

import pytest

# The ui modules import each other by bare name, so ui/ must be on sys.path.
_UI = pathlib.Path(__file__).resolve().parents[2] / "ui"
if str(_UI) not in sys.path:
    sys.path.insert(0, str(_UI))

import _sidebar as sb  # noqa: E402
import _styles  # noqa: E402


class _Ctx:
    """Minimal context manager standing in for a column or container."""

    def __enter__(self) -> "_Ctx":
        return self

    def __exit__(self, *args: object) -> bool:
        return False


def test_center_shows_age_for_both_semantics() -> None:
    # One semantic: the center is the data's age, scheduled or on demand.
    scheduled = sb._freshness_circle_html("Features", 3600.0, scheduled=True)
    on_demand = sb._freshness_circle_html("Inference", 3600.0, scheduled=False)
    for html in (scheduled, on_demand):
        assert ">1h 0m</div>" in html


def test_scheduled_ring_states_and_subtitles() -> None:
    cycle = sb._PREDICTION_CYCLE_SECONDS
    fresh = sb._freshness_circle_html("F", 0.2 * cycle, scheduled=True)
    aging = sb._freshness_circle_html("F", 0.8 * cycle, scheduled=True)
    overdue = sb._freshness_circle_html("F", 1.5 * cycle, scheduled=True)

    assert sb._RING_FRESH in fresh and "next in" in fresh
    assert sb._RING_AGING in aging and "next in" in aging
    assert sb._RING_OVERDUE in overdue and "overdue" in overdue
    # Overdue draws the full unbroken ring: no dash gap, so no notch or seam.
    assert "stroke-dasharray" not in overdue


def test_ring_is_svg_with_rounded_caps_not_conic() -> None:
    html = sb._freshness_circle_html("F", 4000.0, scheduled=True)
    assert "<svg" in html
    assert 'stroke-linecap="round"' in html
    assert "conic-gradient" not in html


def test_on_demand_ring_is_continuous_and_idle() -> None:
    # The on-demand dial now draws a continuous idle-colored ring, not dashes.
    html = sb._freshness_circle_html("I", 7200.0, scheduled=False)
    assert "stroke-dasharray" not in html
    assert sb._RING_IDLE in html
    assert "on demand" in html


def test_interactive_dial_swaps_age_for_run() -> None:
    interactive = sb._freshness_circle_html(
        "Features", 100.0, scheduled=True, interactive=True
    )
    plain = sb._freshness_circle_html("Features", 100.0, scheduled=True)
    assert 'class="fc-age"' in interactive
    assert 'class="fc-run"' in interactive and ">Run</span>" in interactive
    # A non-interactive dial carries no Run label, only the age.
    assert "fc-run" not in plain


def test_dial_exposes_hover_hook_classes() -> None:
    html = sb._freshness_circle_html("F", 4000.0, scheduled=True)
    assert 'class="fc-ring"' in html
    assert 'class="fc-ring-arc"' in html
    assert 'class="fc-disc"' in html


def test_dial_button_triggers_and_toasts(monkeypatch: pytest.MonkeyPatch) -> None:
    keys: list[str | None] = []
    toasts: list[str] = []
    monkeypatch.setattr(sb.st, "session_state", {})
    monkeypatch.setattr(sb, "pipeline_run_states", _run_states_stub())
    reruns: list[str] = []
    monkeypatch.setattr(sb.st, "button", _recording_button(keys, clicked=True))
    monkeypatch.setattr(sb.st, "toast", lambda msg: toasts.append(msg))
    monkeypatch.setattr(sb.st, "rerun", lambda scope: reruns.append(scope))
    monkeypatch.setattr(sb, "trigger_pipeline_run", lambda pipeline: ("run-7", None))

    sb._render_dial_button("Features", "feature")
    assert keys == ["run_feature"]
    assert toasts == ["Features: queued run-7"]
    # A successful trigger flags the pipeline busy and reruns the fragment.
    assert "feature" in sb.st.session_state["fc_queued"]
    assert reruns == ["fragment"]


def test_dial_button_failure_toast(monkeypatch: pytest.MonkeyPatch) -> None:
    toasts: list[str] = []
    monkeypatch.setattr(sb.st, "button", _recording_button([], clicked=True))
    monkeypatch.setattr(sb.st, "toast", lambda msg: toasts.append(msg))
    monkeypatch.setattr(sb, "trigger_pipeline_run", lambda pipeline: (None, "boom"))

    sb._render_dial_button("Training", "training")
    assert toasts == ["Training trigger failed — boom"]


def test_cascade_button_triggers_with_short_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    keys: list[str | None] = []
    toasts: list[str] = []
    monkeypatch.setattr(sb.st, "session_state", {})
    monkeypatch.setattr(sb, "pipeline_run_states", _run_states_stub())
    reruns: list[str] = []
    monkeypatch.setattr(sb.st, "button", _recording_button(keys, clicked=True))
    monkeypatch.setattr(sb.st, "toast", lambda msg: toasts.append(msg))
    monkeypatch.setattr(sb.st, "rerun", lambda scope: reruns.append(scope))
    monkeypatch.setattr(
        sb, "trigger_pipeline_run", lambda pipeline: ("proj/loc/exec-3", None)
    )

    sb._render_cascade_button()
    assert keys == ["run_cascade"]
    assert toasts == ["Cascade queued — exec-3"]
    # The cascade flags all three pipelines busy at once and reruns the fragment.
    assert set(sb.st.session_state["fc_queued"]) == {"feature", "training", "inference"}
    assert reruns == ["fragment"]


def test_freshness_bar_gates_buttons_and_uses_no_popover(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    keys: list[str | None] = []
    popovers: list[object] = []
    _patch_bar(monkeypatch, keys, capabilities=["feature", "cascade"])
    monkeypatch.setattr(sb.st, "popover", lambda *a, **k: popovers.append(a))

    sb._render_freshness_bar()
    assert "run_feature" in keys and "run_cascade" in keys
    assert "run_training" not in keys and "run_inference" not in keys
    assert popovers == []  # no popover remains in the sidebar


def test_freshness_bar_all_pipelines_capable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    keys: list[str | None] = []
    _patch_bar(
        monkeypatch, keys, capabilities=["feature", "training", "inference", "cascade"]
    )

    sb._render_freshness_bar()
    assert keys == ["run_feature", "run_training", "run_inference", "run_cascade"]


def test_latest_states_maps_newest_first_and_ignores_errors() -> None:
    ok = sb.ControlRuns(
        runs=[
            {"run_id": "b", "pipeline": "inference", "state": "running"},
            {"run_id": "a", "pipeline": "inference", "state": "success"},
            {"run_id": "c", "pipeline": "feature", "state": "queued"},
        ]
    )
    # Newest-first input, so the first run seen per pipeline is the current one.
    assert sb._latest_states(ok) == {"inference": "running", "feature": "queued"}
    # An errored control plane reports nothing busy from the poll.
    errored = sb.ControlRuns(runs=[], error="serving API unreachable")
    assert sb._latest_states(errored) == {}


def test_busy_from_poll_disables_dims_and_subtitles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    keys: list[str | None] = []
    calls: list[dict] = []
    htmls: list[str] = []
    _patch_bar(
        monkeypatch,
        keys,
        capabilities=["feature", "training", "cascade"],
        run_states={"feature": "running"},
        htmls=htmls,
        calls=calls,
    )

    sb._render_freshness_bar()

    disabled = {c["key"]: c["disabled"] for c in calls}
    assert disabled["run_feature"] is True
    assert disabled["run_training"] is False
    assert disabled["run_cascade"] is True  # cascade off while any pipeline is busy
    # The busy dial dims (fc-busy) and its subtitle reports the polled state.
    assert any("fc-busy" in h and "Features<br/>running" in h for h in htmls)
    assert not any("fc-busy" in h and "Training" in h for h in htmls)


def test_busy_from_session_flag_renders_queued(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    keys: list[str | None] = []
    calls: list[dict] = []
    htmls: list[str] = []
    _patch_bar(
        monkeypatch,
        keys,
        capabilities=["feature", "cascade"],
        run_states={},  # poll empty, e.g. the control plane errored
        htmls=htmls,
        calls=calls,
    )
    sb.st.session_state["fc_queued"] = {"feature": sb._time.time()}

    sb._render_freshness_bar()

    disabled = {c["key"]: c["disabled"] for c in calls}
    assert disabled["run_feature"] is True
    assert disabled["run_cascade"] is True
    # Flag-only busy reads 'queued' until Airflow materializes the run.
    assert any("fc-busy" in h and "Features<br/>queued" in h for h in htmls)


def test_busy_flag_expires_after_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    keys: list[str | None] = []
    calls: list[dict] = []
    htmls: list[str] = []
    fixed = 10_000.0
    monkeypatch.setattr(sb, "_time", types.SimpleNamespace(time=lambda: fixed))
    _patch_bar(
        monkeypatch,
        keys,
        capabilities=["feature", "cascade"],
        run_states={},
        htmls=htmls,
        calls=calls,
    )
    sb.st.session_state["fc_queued"] = {"feature": fixed - sb._QUEUED_FLAG_TTL - 1}

    sb._render_freshness_bar()

    disabled = {c["key"]: c["disabled"] for c in calls}
    assert disabled["run_feature"] is False
    assert disabled["run_cascade"] is False
    assert not any("fc-busy" in h for h in htmls)
    # The stale flag is pruned, so it cannot linger past its TTL.
    assert "feature" not in sb.st.session_state["fc_queued"]


def test_control_plane_error_leaves_bar_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    keys: list[str | None] = []
    calls: list[dict] = []
    _patch_bar(
        monkeypatch,
        keys,
        capabilities=["feature", "training", "inference", "cascade"],
        run_states={},  # pipeline_run_states returns {} when control_runs errors
        calls=calls,
    )

    sb._render_freshness_bar()

    # A dead control plane never greys the bar from the poll alone.
    assert all(c["disabled"] is False for c in calls)


def test_dial_hover_css_emitted() -> None:
    css = _styles._CSS
    assert "st-key-dialwrap_" in css
    # The swap is guarded to :enabled, so a disabled (busy) button never fires it.
    assert ":has(button:enabled:hover)" in css
    assert ":has(button:hover)" not in css
    assert ".fc-run" in css
    assert "cursor: pointer" in css
    # The removed popovers leave no dead popover-button CSS behind.
    assert "stPopoverButton" not in css


def test_busy_css_dims_dial_and_resets_cursor() -> None:
    css = _styles._CSS
    # A busy dial dims and desaturates; the disabled overlay drops the pointer.
    assert ".fc-busy" in css
    assert "grayscale" in css
    assert "button:disabled" in css


def _recording_button(keys: list, *, clicked: bool, calls: list | None = None):
    def button(label: str, **kw: object) -> bool:
        keys.append(kw.get("key"))
        if calls is not None:
            calls.append(
                {"key": kw.get("key"), "disabled": bool(kw.get("disabled", False))}
            )
        return clicked

    return button


def _run_states_stub(states: dict[str, str] | None = None):
    """Stand in for the cached run-states probe, with a no-op .clear()."""
    resolved = states or {}

    def probe() -> dict[str, str]:
        return resolved

    def clear() -> None:
        pass

    probe.clear = clear
    return probe


def _patch_bar(
    monkeypatch: pytest.MonkeyPatch,
    keys: list,
    *,
    capabilities: list[str],
    run_states: dict[str, str] | None = None,
    htmls: list | None = None,
    calls: list | None = None,
) -> None:
    monkeypatch.setattr(sb.st, "columns", lambda n: [_Ctx() for _ in range(n)])
    monkeypatch.setattr(sb.st, "container", lambda **kw: _Ctx())
    monkeypatch.setattr(sb.st, "session_state", {})

    def _markdown(*a: object, **k: object) -> None:
        if htmls is not None and a:
            htmls.append(a[0])

    monkeypatch.setattr(sb.st, "markdown", _markdown)
    monkeypatch.setattr(sb.st, "toast", lambda *a, **k: None)
    monkeypatch.setattr(
        sb.st, "button", _recording_button(keys, clicked=False, calls=calls)
    )
    monkeypatch.setattr(sb, "prom_query_batch", lambda exprs: [1000.0, 1000.0, 1000.0])
    monkeypatch.setattr(sb, "pipeline_capabilities", lambda: capabilities)
    monkeypatch.setattr(sb, "pipeline_run_states", _run_states_stub(run_states))
