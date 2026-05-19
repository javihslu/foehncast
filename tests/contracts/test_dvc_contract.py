"""Contract tests for dvc.yaml and the DVC stage entry points."""

from __future__ import annotations

from pathlib import Path

import yaml

from tests.repo_helpers import read_repo_text

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _load_dvc_yaml() -> dict:
    return yaml.safe_load(read_repo_text("dvc.yaml"))


# ---------------------------------------------------------------------------
# 1. DVC pipeline structure
# ---------------------------------------------------------------------------


def test_dvc_yaml_defines_curate_and_train_stages() -> None:
    dvc = _load_dvc_yaml()
    assert "curate" in dvc["stages"]
    assert "train" in dvc["stages"]


def test_dvc_curate_stage_depends_on_feature_pipeline_sources() -> None:
    dvc = _load_dvc_yaml()
    deps = dvc["stages"]["curate"]["deps"]
    assert "src/foehncast/feature_pipeline/ingest.py" in deps
    assert "src/foehncast/feature_pipeline/engineer.py" in deps
    assert "src/foehncast/feature_pipeline/validate.py" in deps
    assert "config.yaml" in deps


def test_dvc_train_stage_depends_on_curated_data() -> None:
    dvc = _load_dvc_yaml()
    deps = dvc["stages"]["train"]["deps"]
    assert any("data/" in dep for dep in deps), (
        "Train stage must depend on curated data output"
    )


def test_dvc_train_stage_depends_on_training_pipeline_sources() -> None:
    dvc = _load_dvc_yaml()
    deps = dvc["stages"]["train"]["deps"]
    assert "src/foehncast/training_pipeline/train.py" in deps
    assert "src/foehncast/training_pipeline/evaluate.py" in deps
    assert "src/foehncast/training_pipeline/label.py" in deps


def test_dvc_train_stage_produces_metrics() -> None:
    dvc = _load_dvc_yaml()
    metrics = dvc["stages"]["train"]["metrics"]
    metric_paths = [m if isinstance(m, str) else list(m.keys())[0] for m in metrics]
    assert any("train_metrics.json" in p for p in metric_paths)


# ---------------------------------------------------------------------------
# 2. DVC stages use the shared entry point
# ---------------------------------------------------------------------------


def test_dvc_curate_command_uses_dvc_stages_module() -> None:
    dvc = _load_dvc_yaml()
    cmd = dvc["stages"]["curate"]["cmd"]
    assert "foehncast.dvc_stages" in cmd
    assert "curate" in cmd


def test_dvc_train_command_uses_dvc_stages_module() -> None:
    dvc = _load_dvc_yaml()
    cmd = dvc["stages"]["train"]["cmd"]
    assert "foehncast.dvc_stages" in cmd
    assert "train" in cmd


# ---------------------------------------------------------------------------
# 3. DVC stages align with pipeline stage boundaries
# ---------------------------------------------------------------------------


def test_dvc_curate_covers_feature_pipeline_stages() -> None:
    """Curate stage depends on ingest, engineer, validate."""
    dvc = _load_dvc_yaml()
    deps = dvc["stages"]["curate"]["deps"]
    dep_text = " ".join(deps)
    assert "ingest" in dep_text, "curate must depend on fetch/ingest source"
    assert "engineer" in dep_text, "curate must depend on engineer source"
    assert "validate" in dep_text, "curate must depend on validate source"


def test_dvc_train_covers_training_pipeline_stages() -> None:
    """Train stage depends on train, evaluate, label."""
    dvc = _load_dvc_yaml()
    deps = dvc["stages"]["train"]["deps"]
    dep_text = " ".join(deps)
    assert "train" in dep_text
    assert "evaluate" in dep_text
    assert "label" in dep_text


# ---------------------------------------------------------------------------
# 4. DVC remote configuration
# ---------------------------------------------------------------------------


def test_dvc_config_defines_local_objectstore_remote() -> None:
    config_text = read_repo_text(".dvc/config")
    assert "local-objectstore" in config_text
    assert "s3://foehncast-data/dvc" in config_text


def test_dvc_config_uses_minio_endpoint() -> None:
    config_text = read_repo_text(".dvc/config")
    assert "endpointurl" in config_text
    assert "127.0.0.1:9000" in config_text


# ---------------------------------------------------------------------------
# 5. DVC entry point module exists and is importable
# ---------------------------------------------------------------------------


def test_dvc_stages_module_is_importable() -> None:
    from foehncast import dvc_stages

    assert hasattr(dvc_stages, "curate")
    assert hasattr(dvc_stages, "train")
    assert hasattr(dvc_stages, "main")


# ---------------------------------------------------------------------------
# 6. DVC param keys actually exist in config.yaml
# ---------------------------------------------------------------------------


def test_dvc_params_reference_valid_config_keys() -> None:
    """Catch typos like rider_profile vs rider in DVC param references."""
    dvc = _load_dvc_yaml()
    config = yaml.safe_load((REPO_ROOT / "config.yaml").read_text())

    for stage_name, stage in dvc["stages"].items():
        for param_entry in stage.get("params", []):
            if not isinstance(param_entry, dict):
                continue
            for _file, keys in param_entry.items():
                if keys is None:
                    continue
                for key in keys:
                    # walk dotted keys like "model.features"
                    node = config
                    for part in key.split("."):
                        assert isinstance(node, dict) and part in node, (
                            f"{stage_name}: param '{key}' not in config.yaml"
                        )
                        node = node[part]


# ---------------------------------------------------------------------------
# 7. DVC source dependencies exist on disk
# ---------------------------------------------------------------------------


def test_dvc_source_deps_exist() -> None:
    """Every src/ dependency referenced in dvc.yaml must exist."""
    dvc = _load_dvc_yaml()
    missing = []
    for name, stage in dvc["stages"].items():
        for dep in stage.get("deps", []):
            if dep.startswith("src/") and not (REPO_ROOT / dep).exists():
                missing.append(f"{name}: {dep}")
    assert not missing, f"Missing source dependencies: {missing}"


def test_dvc_lockfile_exists() -> None:
    """dvc.lock must be committed alongside dvc.yaml."""
    assert (REPO_ROOT / "dvc.lock").exists(), (
        "dvc.lock is missing — run 'dvc repro' to generate it"
    )
