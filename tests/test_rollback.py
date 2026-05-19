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


def test_main_passes_cli_args_to_rollback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    logged: dict[str, object] = {}

    monkeypatch.setattr(
        rollback,
        "assign_model_alias",
        lambda alias, version, model_name=None: logged.update(
            {"rollback": (alias, version, model_name)}
        ),
    )
    monkeypatch.setattr(
        "sys.argv",
        ["rollback", "--version", "5", "--target-alias", "champion"],
    )

    rollback.main()

    assert logged["rollback"] == ("champion", "5", None)
    assert capsys.readouterr().out.strip() == "5"
