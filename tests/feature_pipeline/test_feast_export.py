"""Tests for Feast export helpers."""

from __future__ import annotations

from pathlib import Path
import subprocess

import pandas as pd
import pytest

from foehncast.feature_pipeline import feast


def test_to_feast_frame_uses_datetime_index() -> None:
    index = pd.date_range("2025-01-01T00:00:00", periods=2, freq="h")
    features_df = pd.DataFrame({"wind_speed_10m": [10.0, 12.0]}, index=index)

    result = feast._to_feast_frame(features_df, spot_id="silvaplana")

    assert list(result.columns) == ["event_timestamp", "wind_speed_10m", "spot_id"]
    assert result["spot_id"].tolist() == ["silvaplana", "silvaplana"]
    assert str(result["event_timestamp"].dtype).startswith("datetime64[ns, UTC]")


def test_build_offline_store_frame_combines_spots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = pd.date_range("2025-01-01T00:00:00", periods=2, freq="h")
    silvaplana = pd.DataFrame({"wind_speed_10m": [10.0, 12.0]}, index=index)
    urnersee = pd.DataFrame({"wind_speed_10m": [14.0, 16.0]}, index=index)

    monkeypatch.setattr(
        feast,
        "get_spots",
        lambda: [{"id": "silvaplana"}, {"id": "urnersee"}, {"id": "missing"}],
    )

    def _read_features(spot_id: str, dataset: str) -> pd.DataFrame:
        if spot_id == "silvaplana":
            return silvaplana
        if spot_id == "urnersee":
            return urnersee
        raise FileNotFoundError(spot_id)

    monkeypatch.setattr(feast, "read_features", _read_features)

    result = feast.build_offline_store_frame(dataset="train")

    assert result["spot_id"].tolist() == [
        "silvaplana",
        "urnersee",
        "silvaplana",
        "urnersee",
    ]
    assert "event_timestamp" in result.columns
    assert len(result) == 4


def test_export_offline_store_writes_parquet(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    frame = pd.DataFrame(
        {
            "spot_id": ["silvaplana"],
            "event_timestamp": pd.to_datetime(["2025-01-01T00:00:00Z"]),
            "wind_speed_10m": [12.0],
        }
    )
    monkeypatch.setattr(feast, "build_offline_store_frame", lambda dataset: frame)

    destination = feast.export_offline_store(
        dataset="train", output_path=tmp_path / "feast" / "train.parquet"
    )

    result = pd.read_parquet(destination)
    pd.testing.assert_frame_equal(result, frame)


def test_export_offline_store_uses_canonical_default_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    frame = pd.DataFrame(
        {
            "spot_id": ["silvaplana"],
            "event_timestamp": pd.to_datetime(["2025-01-01T00:00:00Z"]),
            "wind_speed_10m": [12.0],
        }
    )
    expected = tmp_path / "data" / "feast" / "train.parquet"

    monkeypatch.setattr(feast, "build_offline_store_frame", lambda dataset: frame)
    monkeypatch.setattr(feast, "feast_offline_path", lambda dataset: expected)

    destination = feast.export_offline_store(dataset="train")

    assert destination == expected
    result = pd.read_parquet(destination)
    pd.testing.assert_frame_equal(result, frame)


def test_export_offline_store_replaces_non_writable_existing_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    frame = pd.DataFrame(
        {
            "spot_id": ["silvaplana"],
            "event_timestamp": pd.to_datetime(["2025-01-01T00:00:00Z"]),
            "wind_speed_10m": [12.0],
        }
    )
    destination = tmp_path / "feast" / "train.parquet"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("stale", encoding="utf-8")
    destination.chmod(0o444)

    monkeypatch.setattr(feast, "build_offline_store_frame", lambda dataset: frame)

    rendered_path = feast.export_offline_store(dataset="train", output_path=destination)

    assert rendered_path == destination
    result = pd.read_parquet(rendered_path)
    pd.testing.assert_frame_equal(result, frame)


def test_prepare_feature_store_applies_repo_and_materializes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    export_destination = tmp_path / "data" / "feast" / "train.parquet"
    config_path = tmp_path / ".state" / "feast" / "feature_store.runtime.yaml"
    repo_path = tmp_path / "feature_repo"
    repo_path.mkdir()
    commands: list[tuple[list[str], Path, str, str]] = []

    monkeypatch.setattr(
        feast,
        "export_offline_store",
        lambda dataset, output_path=None: (
            Path(output_path) if output_path else export_destination
        ),
    )
    monkeypatch.setattr(feast, "render_runtime_config", lambda: config_path)
    monkeypatch.setattr(feast, "require_existing_feast_repo_path", lambda: repo_path)

    def _record_command(args: list[str], *, cwd: Path, env: dict[str, str]) -> None:
        commands.append(
            (
                args,
                cwd,
                env["FOEHNCAST_FEAST_CONFIG_PATH"],
                env["FEAST_FS_YAML_FILE_PATH"],
            )
        )

    monkeypatch.setattr(feast, "_run_feast_cli", _record_command)

    result = feast.prepare_feature_store(
        dataset="train",
        output_path=export_destination,
        materialize_timestamp="2026-05-12T13:00:00+00:00",
    )

    assert commands == [
        (
            ["apply"],
            repo_path,
            str(config_path),
            str(config_path),
        ),
        (
            ["materialize-incremental", "2026-05-12T13:00:00+00:00"],
            repo_path,
            str(config_path),
            str(config_path),
        ),
    ]
    assert result == {
        "dataset": "train",
        "output_path": str(export_destination),
        "config_path": str(config_path),
        "repo_path": str(repo_path),
        "materialized": True,
        "materialize_timestamp": "2026-05-12T13:00:00+00:00",
    }


def test_prepare_feature_store_skips_export_for_bigquery_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config_path = tmp_path / ".state" / "feast" / "feature_store.runtime.yaml"
    repo_path = tmp_path / "feature_repo"
    repo_path.mkdir()
    monkeypatch.setenv("FOEHNCAST_FEAST_SOURCE", "bigquery")

    def _unexpected_export(*args: object, **kwargs: object) -> Path:
        raise AssertionError("export_offline_store must not run for the BigQuery source")

    monkeypatch.setattr(feast, "export_offline_store", _unexpected_export)
    monkeypatch.setattr(feast, "render_runtime_config", lambda: config_path)
    monkeypatch.setattr(feast, "require_existing_feast_repo_path", lambda: repo_path)

    commands: list[list[str]] = []
    monkeypatch.setattr(
        feast,
        "_run_feast_cli",
        lambda args, *, cwd, env: commands.append(args),
    )

    result = feast.prepare_feature_store(
        dataset="forecast", materialize_timestamp="2026-05-12T13:00:00+00:00"
    )

    assert [command[0] for command in commands] == ["apply", "materialize-incremental"]
    assert result["output_path"] is None
    assert result["materialized"] is True


def test_prepare_feature_store_can_skip_materialize(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    export_destination = tmp_path / "data" / "feast" / "train.parquet"
    config_path = tmp_path / ".state" / "feast" / "feature_store.runtime.yaml"
    repo_path = tmp_path / "feature_repo"
    repo_path.mkdir()
    commands: list[list[str]] = []

    monkeypatch.setattr(
        feast,
        "export_offline_store",
        lambda dataset, output_path=None: (
            Path(output_path) if output_path else export_destination
        ),
    )
    monkeypatch.setattr(feast, "render_runtime_config", lambda: config_path)
    monkeypatch.setattr(feast, "require_existing_feast_repo_path", lambda: repo_path)
    monkeypatch.setattr(
        feast,
        "_run_feast_cli",
        lambda args, *, cwd, env: commands.append(args),
    )

    result = feast.prepare_feature_store(dataset="train", materialize=False)

    assert commands == [["apply"]]
    assert result["materialized"] is False
    assert result["materialize_timestamp"] is None


def test_prepare_feature_store_requires_existing_repo_before_export(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _missing_repo() -> Path:
        raise RuntimeError(
            "Configured Feast repo not found at /tmp/missing-feature-repo"
        )

    def _unexpected_export(*args: object, **kwargs: object) -> Path:
        raise AssertionError("offline export should not start before repo validation")

    monkeypatch.setattr(feast, "require_existing_feast_repo_path", _missing_repo)
    monkeypatch.setattr(feast, "export_offline_store", _unexpected_export)

    with pytest.raises(RuntimeError, match="Configured Feast repo not found"):
        feast.prepare_feature_store(dataset="train")


def test_run_feast_cli_prefers_configured_sibling_console_script(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo_path = tmp_path / "feature_repo"
    repo_path.mkdir()
    config_path = tmp_path / "feature_store.runtime.yaml"
    command: list[str] | None = None
    venv_bin = tmp_path / "feast-venv" / "bin"
    python_executable = venv_bin / "python"
    feast_executable = venv_bin / "feast"

    venv_bin.mkdir(parents=True)
    python_executable.write_text("")
    feast_executable.write_text("")

    monkeypatch.setenv("FOEHNCAST_FEAST_PYTHON", str(python_executable))

    def _run(*args, **kwargs):
        nonlocal command
        command = args[0]
        return subprocess.CompletedProcess(args[0], 0)

    monkeypatch.setattr(feast.subprocess, "run", _run)

    feast._run_feast_cli(
        ["apply"],
        cwd=repo_path,
        env=feast.feast_runtime_env(config_path),
    )

    assert command == [str(feast_executable), "apply"]


def test_run_feast_cli_falls_back_to_module_invocation_without_console_script(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo_path = tmp_path / "feature_repo"
    repo_path.mkdir()
    config_path = tmp_path / "feature_store.runtime.yaml"
    command: list[str] | None = None
    venv_bin = tmp_path / "feast-venv" / "bin"
    python_executable = venv_bin / "python"

    venv_bin.mkdir(parents=True)
    python_executable.write_text("")

    monkeypatch.setenv("FOEHNCAST_FEAST_PYTHON", str(python_executable))
    monkeypatch.setattr(feast.shutil, "which", lambda name: None)

    def _run(*args, **kwargs):
        nonlocal command
        command = args[0]
        return subprocess.CompletedProcess(args[0], 0)

    monkeypatch.setattr(feast.subprocess, "run", _run)

    feast._run_feast_cli(
        ["apply"],
        cwd=repo_path,
        env=feast.feast_runtime_env(config_path),
    )

    assert command == [
        str(python_executable),
        "-m",
        "feast",
        "apply",
    ]
