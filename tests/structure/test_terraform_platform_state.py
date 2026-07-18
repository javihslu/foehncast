"""Tests for the terraform platform state repo-variable pair stream."""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_FAKE_TERRAFORM_MINIMAL = """#!/usr/bin/env bash
set -euo pipefail

mode=""
raw_name=""
for arg in "$@"; do
  case "$arg" in
    -json)
      mode="json"
      ;;
    -raw)
      mode="raw"
      ;;
    -chdir=*|output)
      ;;
    *)
      if [[ "$mode" == "raw" && -z "$raw_name" ]]; then
        raw_name="$arg"
      fi
      ;;
  esac
done

if [[ "$mode" == "json" ]]; then
  echo '{"stub":{"value":"stub"}}'
  exit 0
fi

if [[ "$mode" == "raw" ]]; then
  if [[ "$raw_name" == "project_id" ]]; then
    echo "test-project"
    exit 0
  fi
  echo "no output found for ${raw_name}" >&2
  exit 1
fi

echo "unsupported terraform invocation: $*" >&2
exit 1
"""

_FAKE_TERRAFORM_CORRUPTED_ARTIFACT_REPOSITORY = """#!/usr/bin/env bash
set -euo pipefail

mode=""
raw_name=""
for arg in "$@"; do
  case "$arg" in
    -json)
      mode="json"
      ;;
    -raw)
      mode="raw"
      ;;
    -chdir=*|output)
      ;;
    *)
      if [[ "$mode" == "raw" && -z "$raw_name" ]]; then
        raw_name="$arg"
      fi
      ;;
  esac
done

if [[ "$mode" == "json" ]]; then
  echo '{"stub":{"value":"stub"}}'
  exit 0
fi

if [[ "$mode" == "raw" ]]; then
  case "$raw_name" in
    project_id)
      echo "test-project"
      ;;
    artifact_registry_repository_id)
      printf 'foehncast-docker\\nINJECTED garbage\\n'
      ;;
    *)
      echo "stub-value"
      ;;
  esac
  exit 0
fi

echo "unsupported terraform invocation: $*" >&2
exit 1
"""

_FAKE_GH_REFUSES = """#!/usr/bin/env bash
echo "gh should not be invoked in --dry-run mode" >&2
exit 1
"""


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(0o755)


def _path_with_fake_bin(bin_dir: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    return env


def test_terraform_repo_variable_pairs_completes_without_cloud_run_image(
    tmp_path: Path,
) -> None:
    """The pairs stream must reach its final unconditional entry under set -u
    even when no cloud_run_image output or tfvars value is configured."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_executable(bin_dir / "terraform", _FAKE_TERRAFORM_MINIMAL)
    terraform_dir = tmp_path / "terraform"
    terraform_dir.mkdir()

    command = (
        "set -euo pipefail; "
        "source scripts/cli-common.sh; "
        "source scripts/terraform-platform-state.sh; "
        f"terraform_repo_variable_pairs {shlex.quote(str(terraform_dir))}"
    )
    result = subprocess.run(
        ["bash", "-c", command],
        cwd=REPO_ROOT,
        env=_path_with_fake_bin(bin_dir),
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "GCP_PROJECT_ID\ttest-project" in result.stdout
    assert "GCP_PROVISION_CLOUD_WORKFLOWS\t" in result.stdout
    assert "GCP_CLOUD_RUN_IMAGE" not in result.stdout


def test_configure_github_actions_rejects_malformed_variable_name(
    tmp_path: Path,
) -> None:
    """A corrupted pairs stream (embedded newline splitting one entry into
    two) must abort the sync instead of feeding a bogus name to gh."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_executable(bin_dir / "terraform", _FAKE_TERRAFORM_CORRUPTED_ARTIFACT_REPOSITORY)
    _write_executable(bin_dir / "gh", _FAKE_GH_REFUSES)
    terraform_dir = tmp_path / "terraform"
    terraform_dir.mkdir()

    result = subprocess.run(
        [
            "bash",
            "scripts/configure-github-actions.sh",
            "--dry-run",
            "--repo",
            "owner/repo",
            "--terraform-dir",
            str(terraform_dir),
        ],
        cwd=REPO_ROOT,
        env=_path_with_fake_bin(bin_dir),
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "malformed repository variable name" in result.stderr
