"""Tests for the System tab's shadow-divergence chip helper."""

from __future__ import annotations

import pathlib
import sys

_UI = pathlib.Path(__file__).resolve().parents[2] / "ui"
if str(_UI) not in sys.path:
    sys.path.insert(0, str(_UI))

from _system_tab import _SHADOW_EMPTY_CHIP, _shadow_chip  # noqa: E402


def test_shadow_chip_present_when_metric_and_version_available() -> None:
    info = [{"labels": {"champion_version": "10", "candidate_version": "11"}}]

    assert _shadow_chip(0.0312, info) == ("Shadow", "0.031 vs v11")
    assert _shadow_chip(0.000119, info) == ("Shadow", "0.00012 vs v11")


def test_shadow_chip_states_empty_when_divergence_missing() -> None:
    info = [{"labels": {"champion_version": "10", "candidate_version": "11"}}]

    assert _shadow_chip(None, info) == _SHADOW_EMPTY_CHIP


def test_shadow_chip_states_empty_when_info_metric_missing() -> None:
    assert _shadow_chip(0.03, []) == _SHADOW_EMPTY_CHIP


def test_shadow_chip_states_empty_when_candidate_version_label_missing() -> None:
    assert _shadow_chip(0.03, [{"labels": {"champion_version": "10"}}]) == (
        _SHADOW_EMPTY_CHIP
    )


def test_shadow_empty_chip_wording_is_explicit() -> None:
    assert _SHADOW_EMPTY_CHIP == ("Shadow", "no challenger registered")
