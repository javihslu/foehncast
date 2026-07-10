"""Tests for feature-pipeline notebook review parity helpers."""

from __future__ import annotations

import json
from pathlib import Path

from foehncast.feature_pipeline import notebook_review


def _write_summary(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def _summary_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "runtime_lane": "local",
        "storage_backend": "s3",
        "spot_id": "silvaplana",
        "dataset": "notebook_eval",
        "storage_target": "s3://foehncast-data/notebook_eval/silvaplana.parquet",
        "raw_rows": 168,
        "raw_columns": 13,
        "feature_rows": 168,
        "feature_columns": 23,
        "validation_is_valid": True,
        "validation_missing_columns": 0,
        "validation_range_violations": 0,
        "stored_rows": 168,
        "stored_columns": 23,
        "roundtrip_contract_valid": True,
        "max_numeric_abs_delta": 0.0,
        "feast_roundtrip_ready": True,
        "offline_rows": 168,
        "offline_columns": 25,
        "entity_rows": 168,
        "entity_columns": 2,
        "exported_path": "/tmp/feast/notebook_eval_s3.parquet",
    }
    payload.update(overrides)
    return payload


def test_feature_pipeline_notebook_summary_path_uses_state_dir(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(notebook_review, "project_root", lambda: tmp_path)

    assert notebook_review.feature_pipeline_notebook_review_dir() == (
        tmp_path / ".state" / "notebook_reviews"
    )
    assert notebook_review.feature_pipeline_notebook_summary_path("s3") == (
        tmp_path / ".state" / "notebook_reviews" / "feature_pipeline_summary_s3.json"
    )


def test_compare_feature_pipeline_notebook_summaries_reports_pass(
    tmp_path: Path,
) -> None:
    review_dir = tmp_path / "notebook_reviews"
    _write_summary(
        review_dir / "feature_pipeline_summary_s3.json",
        _summary_payload(),
    )
    _write_summary(
        review_dir / "feature_pipeline_summary_bigquery.json",
        _summary_payload(
            runtime_lane="cloud",
            storage_backend="bigquery",
            storage_target="your-gcp-project.analytics.notebook_eval",
            exported_path="/tmp/feast/notebook_eval_bigquery.parquet",
        ),
    )

    report = notebook_review.compare_feature_pipeline_notebook_summaries(
        "s3",
        review_dir=review_dir,
    )

    assert report["status"] == "pass"
    assert report["all_match"] is True
    assert report["mismatched_fields"] == []
    assert report["counterpart_backend"] == "bigquery"
    assert report["expected_differences"] == [
        {
            "field": "runtime_lane",
            "current": "local",
            "counterpart": "cloud",
        },
        {
            "field": "storage_backend",
            "current": "s3",
            "counterpart": "bigquery",
        },
        {
            "field": "storage_target",
            "current": "s3://foehncast-data/notebook_eval/silvaplana.parquet",
            "counterpart": "your-gcp-project.analytics.notebook_eval",
        },
        {
            "field": "exported_path",
            "current": "/tmp/feast/notebook_eval_s3.parquet",
            "counterpart": "/tmp/feast/notebook_eval_bigquery.parquet",
        },
    ]


def test_compare_feature_pipeline_notebook_summaries_reports_mismatch(
    tmp_path: Path,
) -> None:
    review_dir = tmp_path / "notebook_reviews"
    _write_summary(
        review_dir / "feature_pipeline_summary_s3.json",
        _summary_payload(),
    )
    _write_summary(
        review_dir / "feature_pipeline_summary_bigquery.json",
        _summary_payload(
            runtime_lane="cloud",
            storage_backend="bigquery",
            storage_target="your-gcp-project.analytics.notebook_eval",
            exported_path="/tmp/feast/notebook_eval_bigquery.parquet",
            feature_rows=167,
        ),
    )

    report = notebook_review.compare_feature_pipeline_notebook_summaries(
        "s3",
        review_dir=review_dir,
    )

    assert report["status"] == "fail"
    assert report["all_match"] is False
    assert report["mismatched_fields"] == ["feature_rows"]
    assert next(
        row for row in report["comparison"] if row["field"] == "feature_rows"
    ) == {
        "field": "feature_rows",
        "current": 168,
        "counterpart": 167,
        "present_in_current": True,
        "present_in_counterpart": True,
        "matches": False,
    }


def test_run_cli_reports_missing_counterpart_summary(
    tmp_path: Path,
    capsys,
) -> None:
    review_dir = tmp_path / "notebook_reviews"
    _write_summary(
        review_dir / "feature_pipeline_summary_s3.json",
        _summary_payload(),
    )

    exit_code = notebook_review.run_cli(
        ["compare", "--backend", "s3", "--review-dir", str(review_dir)]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "feature_pipeline_summary_bigquery.json" in captured.err


def test_run_cli_prints_json_report_on_success(
    tmp_path: Path,
    capsys,
) -> None:
    review_dir = tmp_path / "notebook_reviews"
    _write_summary(
        review_dir / "feature_pipeline_summary_s3.json",
        _summary_payload(),
    )
    _write_summary(
        review_dir / "feature_pipeline_summary_bigquery.json",
        _summary_payload(
            runtime_lane="cloud",
            storage_backend="bigquery",
            storage_target="your-gcp-project.analytics.notebook_eval",
            exported_path="/tmp/feast/notebook_eval_bigquery.parquet",
        ),
    )

    exit_code = notebook_review.run_cli(
        ["compare", "--backend", "s3", "--review-dir", str(review_dir)]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload["status"] == "pass"
    assert payload["backend"] == "s3"
    assert payload["counterpart_backend"] == "bigquery"
