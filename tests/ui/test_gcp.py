"""Test the cloud-runtime switch that picks the UI orchestration backend."""

from __future__ import annotations

import pathlib
import sys

import pytest

# ui modules import each other by bare name, so ui/ must be on sys.path.
_UI = pathlib.Path(__file__).resolve().parents[2] / "ui"
if str(_UI) not in sys.path:
    sys.path.insert(0, str(_UI))

from _gcp import in_cloud_runtime  # noqa: E402


def test_in_cloud_runtime_true_on_cloud_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("K_SERVICE", "foehncast-ui")
    assert in_cloud_runtime() is True


def test_in_cloud_runtime_false_locally(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("K_SERVICE", raising=False)
    assert in_cloud_runtime() is False
