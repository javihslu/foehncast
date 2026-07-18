"""Tests for the targeted feast apply retry in scripts/cli-common.sh."""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_FAKE_UV_TRANSIENT_RECOVERS = """#!/usr/bin/env bash
set -euo pipefail

if [[ "$*" == "run --group feast feast apply" ]]; then
  printf 'attempt\\n' >> "$FAKE_UV_ATTEMPTS_FILE"
  attempt_count="$(wc -l < "$FAKE_UV_ATTEMPTS_FILE")"
  if (( attempt_count < 3 )); then
    echo "FileNotFoundError: [Errno 2] No such file or directory: 'features.parquet'" >&2
    exit 1
  fi
  exit 0
fi

echo "unexpected uv invocation: $*" >&2
exit 1
"""

_FAKE_UV_REAL_ERROR = """#!/usr/bin/env bash
set -euo pipefail

if [[ "$*" == "run --group feast feast apply" ]]; then
  printf 'attempt\\n' >> "$FAKE_UV_ATTEMPTS_FILE"
  echo "ValueError: bad feature view config" >&2
  exit 1
fi

echo "unexpected uv invocation: $*" >&2
exit 1
"""


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(0o755)


def _path_with_fake_bin(bin_dir: Path, attempts_file: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["FAKE_UV_ATTEMPTS_FILE"] = str(attempts_file)
    return env


def _run_apply(repo_dir: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    command = (
        "set -euo pipefail; "
        "source scripts/cli-common.sh; "
        f'run_feast_repo_apply_and_maybe_materialize {shlex.quote(str(repo_dir))} false ""'
    )
    return subprocess.run(
        ["bash", "-c", command],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def test_transient_parquet_race_recovers_within_three_attempts(tmp_path: Path) -> None:
    """The known CI race (parquet visibility) must be retried, not treated as
    a hard failure, as long as it clears within the attempt budget."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_executable(bin_dir / "uv", _FAKE_UV_TRANSIENT_RECOVERS)
    attempts_file = tmp_path / "attempts.log"
    repo_dir = tmp_path / "feature_repo"
    repo_dir.mkdir()

    result = _run_apply(repo_dir, _path_with_fake_bin(bin_dir, attempts_file))

    assert result.returncode == 0, result.stderr
    assert len(attempts_file.read_text().splitlines()) == 3


def test_non_transient_error_fails_fast_without_retrying(tmp_path: Path) -> None:
    """A real feast configuration error must not be masked behind repeated
    identical retries; it should surface immediately with its message."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_executable(bin_dir / "uv", _FAKE_UV_REAL_ERROR)
    attempts_file = tmp_path / "attempts.log"
    repo_dir = tmp_path / "feature_repo"
    repo_dir.mkdir()

    result = _run_apply(repo_dir, _path_with_fake_bin(bin_dir, attempts_file))

    assert result.returncode != 0
    assert len(attempts_file.read_text().splitlines()) == 1
    assert "ValueError: bad feature view config" in result.stderr
