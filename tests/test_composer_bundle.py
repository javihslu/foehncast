"""Tests for the Cloud Composer DAG bundle builder."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import foehncast.composer_bundle as composer_bundle


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_build_composer_bundle_flattens_dag_entrypoints_and_copies_sources(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "dags" / "feature_dag.py", "print('feature')\n")
    _write(tmp_path / "dags" / "training_dag.py", "print('training')\n")
    _write(tmp_path / "src" / "foehncast" / "__init__.py", "")
    _write(tmp_path / "src" / "foehncast" / "paths.py", "PROJECT = 'ok'\n")
    _write(tmp_path / "config.yaml", "storage: {}\n")
    _write(tmp_path / "pyproject.toml", "[project]\nname = 'foehncast'\n")
    _write(tmp_path / "feature_repo" / "feature_store.yaml", "project: foehncast\n")
    _write(tmp_path / "feature_repo" / "features.py", "ENTITIES = []\n")

    manifest = composer_bundle.build_composer_bundle(
        tmp_path / "bundle",
        project_root=tmp_path,
    )

    assert (tmp_path / "bundle" / "feature_dag.py").is_file()
    assert (tmp_path / "bundle" / "training_dag.py").is_file()
    assert not (tmp_path / "bundle" / "dags").exists()
    assert (tmp_path / "bundle" / "foehncast" / "paths.py").is_file()
    assert (tmp_path / "bundle" / "feature_repo" / "features.py").is_file()
    assert (tmp_path / "bundle" / "config.yaml").is_file()
    assert (tmp_path / "bundle" / "pyproject.toml").is_file()

    assert {entry["target"] for entry in manifest["entries"]} == {
        "feature_dag.py",
        "training_dag.py",
        "foehncast",
        "feature_repo",
        "config.yaml",
        "pyproject.toml",
    }


def test_build_composer_bundle_requires_checked_in_project_contract_files(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "dags" / "feature_dag.py", "print('feature')\n")
    _write(tmp_path / "src" / "foehncast" / "__init__.py", "")
    _write(tmp_path / "config.yaml", "storage: {}\n")
    _write(tmp_path / "feature_repo" / "feature_store.yaml", "project: foehncast\n")

    with pytest.raises(FileNotFoundError, match="pyproject.toml"):
        composer_bundle.build_composer_bundle(
            tmp_path / "bundle", project_root=tmp_path
        )


def test_write_composer_bundle_manifest_persists_stable_json(tmp_path: Path) -> None:
    manifest = {
        "project_root": "/tmp/foehncast",
        "output_dir": "/tmp/foehncast/bundle",
        "entries": [
            {
                "source": "dags/feature_dag.py",
                "target": "feature_dag.py",
                "type": "file",
            }
        ],
    }

    manifest_path = composer_bundle.write_composer_bundle_manifest(
        manifest,
        tmp_path / "bundle-manifest.json",
    )

    persisted = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert persisted == manifest
