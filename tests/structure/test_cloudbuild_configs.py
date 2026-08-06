"""Structural checks for the cloudbuild build and deploy configs."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
IMAGES_CONFIG = REPO_ROOT / "cloudbuild" / "images.yaml"
DEPLOY_CONFIGS = (("app.yaml", 5), ("mlflow.yaml", 1), ("ui.yaml", 1))
PLATFORM_IMAGES = ("foehncast-app", "foehncast-ui", "foehncast-mlflow")


def _step_text(step: dict) -> str:
    """Flatten a build step to one whitespace-normalized string for matching."""
    tokens = [step.get("name", ""), step.get("entrypoint", "")]
    args = step.get("args", [])
    tokens.extend(args if isinstance(args, list) else [args])
    return " ".join(str(token) for token in tokens).replace("\n", " ")


@pytest.fixture(scope="module")
def images_config() -> dict:
    return yaml.safe_load(IMAGES_CONFIG.read_text())


def test_images_config_is_build_only(images_config: dict) -> None:
    for step in images_config["steps"]:
        text = _step_text(step)
        assert "run deploy" not in text
        assert "jobs update" not in text


def test_images_config_builds_and_pushes_each_latest_image(images_config: dict) -> None:
    steps = images_config["steps"]
    listed = images_config["images"]

    for image in PLATFORM_IMAGES:
        tag = f"{image}:latest"
        matching = [_step_text(step) for step in steps if tag in _step_text(step)]
        assert matching, f"no build step references {tag}"
        assert "docker build" in matching[0]
        assert "docker push" in matching[0]
        assert any(tag in entry for entry in listed)


def test_images_config_uses_no_sha_tags(images_config: dict) -> None:
    text = "\n".join(_step_text(step) for step in images_config["steps"])
    assert "sha-" not in text


@pytest.mark.parametrize(("filename", "deploy_count"), DEPLOY_CONFIGS)
def test_deploy_configs_label_every_deploy_with_its_commit(
    filename: str, deploy_count: int
) -> None:
    """Every deploy stamps the commit so the live revision is identifiable."""
    config = yaml.safe_load((REPO_ROOT / "cloudbuild" / filename).read_text())
    deploys = [
        step
        for step in config["steps"]
        if "run deploy" in _step_text(step) or "jobs update" in _step_text(step)
    ]
    assert len(deploys) == deploy_count

    for step in deploys:
        assert "--update-labels=git-sha=${_COMMIT_SHA}" in step["args"]
