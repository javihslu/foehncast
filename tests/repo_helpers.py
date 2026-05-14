"""Shared file-reading helpers for repo-backed contract tests."""

from __future__ import annotations

import json
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


def read_repo_text(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text()


def read_repo_yaml(relative_path: str) -> dict:
    return yaml.safe_load(read_repo_text(relative_path))


def read_repo_json(relative_path: str) -> dict:
    return json.loads(read_repo_text(relative_path))


def read_workflow_yaml(relative_path: str) -> dict:
    workflow = read_repo_yaml(relative_path)
    if True in workflow and "on" not in workflow:
        workflow["on"] = workflow.pop(True)
    return workflow