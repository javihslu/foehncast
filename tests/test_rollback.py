"""Tests for rollback helpers."""

from __future__ import annotations

import pytest

from foehncast.training_pipeline import rollback


def test_rollback_model_version_restores_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logged: dict[str, object] = {}

    monkeypatch.setattr(
        rollback,
        "assign_model_alias",
        lambda alias, version, model_name=None: logged.update(
            {"rollback": (alias, version, model_name)}
        ),
    )

    version = rollback.rollback_model_version("17")

    assert version == "17"
    assert logged["rollback"] == ("champion", "17", None)


def test_rollback_model_version_rejects_empty_version() -> None:
    with pytest.raises(ValueError, match="Model version must be non-empty"):
        rollback.rollback_model_version("  ")


def test_rollback_model_version_rejects_empty_alias() -> None:
    with pytest.raises(ValueError, match="Target alias must be non-empty"):
        rollback.rollback_model_version("17", target_alias="  ")
