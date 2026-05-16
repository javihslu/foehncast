"""Tests for data provenance helpers."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from foehncast.training_pipeline.provenance import (
    get_git_commit,
    hash_dataframe,
    hash_parquet_files,
)


def test_hash_parquet_files_returns_stable_hex_digest(tmp_path: Path) -> None:
    df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
    (tmp_path / "spot_a.parquet").write_bytes(df.to_parquet())
    (tmp_path / "spot_b.parquet").write_bytes(df.to_parquet())

    first = hash_parquet_files(tmp_path)
    second = hash_parquet_files(tmp_path)
    assert first == second
    assert len(first) == 64  # sha256 hex


def test_hash_parquet_files_changes_when_data_changes(tmp_path: Path) -> None:
    df1 = pd.DataFrame({"a": [1, 2]})
    (tmp_path / "spot_a.parquet").write_bytes(df1.to_parquet())
    hash1 = hash_parquet_files(tmp_path)

    df2 = pd.DataFrame({"a": [3, 4]})
    (tmp_path / "spot_a.parquet").write_bytes(df2.to_parquet())
    hash2 = hash_parquet_files(tmp_path)

    assert hash1 != hash2


def test_hash_dataframe_returns_stable_hex_digest() -> None:
    df = pd.DataFrame({"a": [1, 2], "b": [3.0, 4.0]})
    first = hash_dataframe(df)
    second = hash_dataframe(df)
    assert first == second
    assert len(first) == 64


def test_hash_dataframe_changes_when_content_changes() -> None:
    df1 = pd.DataFrame({"a": [1, 2]})
    df2 = pd.DataFrame({"a": [3, 4]})
    assert hash_dataframe(df1) != hash_dataframe(df2)


def test_get_git_commit_returns_short_hash() -> None:
    commit = get_git_commit()
    assert len(commit) >= 7
    assert commit != "unknown"
