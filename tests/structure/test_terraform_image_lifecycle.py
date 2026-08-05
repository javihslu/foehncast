"""Checks that Terraform leaves running Cloud Run images to Cloud Build."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MAIN_TF = REPO_ROOT / "terraform" / "main.tf"

ANY_RESOURCE = re.compile(r'^resource "', re.M)
CLOUD_RUN = re.compile(r'resource "(google_cloud_run_v2_(?:service|job))" "(\w+)"')
IGNORED_IMAGE = re.compile(r"ignore_changes\s*=\s*\[[^\n]*containers\[0\]\.image")


def _cloud_run_blocks() -> dict[str, str]:
    """Split main.tf into the text of each Cloud Run service and job resource."""
    text = MAIN_TF.read_text()
    bounds = [m.start() for m in ANY_RESOURCE.finditer(text)] + [len(text)]
    blocks = {}
    for start, end in zip(bounds[:-1], bounds[1:], strict=True):
        chunk = text[start:end]
        header = CLOUD_RUN.match(chunk)
        if header:
            blocks[f"{header.group(1)}.{header.group(2)}"] = chunk
    return blocks


def test_cloud_run_resources_are_found() -> None:
    assert len(_cloud_run_blocks()) >= 7


def test_terraform_never_reverts_a_deployed_image() -> None:
    for name, block in _cloud_run_blocks().items():
        if "image = local.cloud_run" not in block:
            continue
        assert IGNORED_IMAGE.search(block), (
            f"{name} would revert to its bootstrap image"
        )
