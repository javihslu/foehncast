"""Helpers for feature-pipeline notebook review artifacts and parity checks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Sequence

from foehncast._json import read_json_file
from foehncast.paths import project_root

ReviewDir = str | Path
_VALID_BACKENDS = ("s3", "bigquery")
_EXPECTED_DIFFERENCE_FIELDS = (
    "runtime_lane",
    "storage_backend",
    "storage_target",
    "exported_path",
)

FEATURE_PIPELINE_NOTEBOOK_STABLE_FIELDS = (
    "spot_id",
    "dataset",
    "raw_rows",
    "raw_columns",
    "feature_rows",
    "feature_columns",
    "validation_is_valid",
    "validation_missing_columns",
    "validation_range_violations",
    "stored_rows",
    "stored_columns",
    "roundtrip_contract_valid",
    "max_numeric_abs_delta",
    "feast_roundtrip_ready",
    "offline_rows",
    "offline_columns",
    "entity_rows",
    "entity_columns",
)


def _normalize_backend(backend: str) -> str:
    normalized = backend.strip().lower()
    if normalized not in _VALID_BACKENDS:
        raise ValueError(
            f"Unsupported notebook review backend '{backend}'. "
            f"Expected one of: {', '.join(_VALID_BACKENDS)}"
        )
    return normalized


def _resolve_review_dir(review_dir: ReviewDir | None = None) -> Path:
    if review_dir is None:
        return project_root() / ".state" / "notebook_reviews"
    return Path(review_dir).expanduser()


def feature_pipeline_notebook_review_dir(review_dir: ReviewDir | None = None) -> Path:
    """Return the local directory that stores notebook review summaries."""
    return _resolve_review_dir(review_dir)


def feature_pipeline_notebook_summary_path(
    backend: str,
    *,
    review_dir: ReviewDir | None = None,
) -> Path:
    """Return the backend-tagged notebook summary artifact path."""
    normalized_backend = _normalize_backend(backend)
    return _resolve_review_dir(review_dir) / (
        f"feature_pipeline_summary_{normalized_backend}.json"
    )


def read_feature_pipeline_notebook_summary(
    backend: str,
    *,
    review_dir: ReviewDir | None = None,
) -> dict[str, Any]:
    """Load one backend-tagged notebook summary artifact."""
    summary_path = feature_pipeline_notebook_summary_path(
        backend,
        review_dir=review_dir,
    )
    payload = read_json_file(summary_path)
    if not isinstance(payload, dict):
        raise ValueError(
            "Feature-pipeline notebook summary must decode to a JSON object."
        )
    return dict(payload)


def counterpart_backend(backend: str) -> str:
    """Return the opposite runtime backend for notebook parity checks."""
    normalized_backend = _normalize_backend(backend)
    return "bigquery" if normalized_backend == "s3" else "s3"


def _values_match(field: str, current_value: object, other_value: object) -> bool:
    if field == "max_numeric_abs_delta":
        return abs(float(current_value) - float(other_value)) < 1e-12
    return current_value == other_value


def compare_feature_pipeline_notebook_summaries(
    backend: str,
    *,
    counterpart_backend_name: str | None = None,
    review_dir: ReviewDir | None = None,
    stable_fields: Sequence[str] = FEATURE_PIPELINE_NOTEBOOK_STABLE_FIELDS,
) -> dict[str, Any]:
    """Compare stable notebook-review fields across the two runtime backends."""
    normalized_backend = _normalize_backend(backend)
    resolved_counterpart = _normalize_backend(
        counterpart_backend_name or counterpart_backend(normalized_backend)
    )

    current_path = feature_pipeline_notebook_summary_path(
        normalized_backend,
        review_dir=review_dir,
    )
    other_path = feature_pipeline_notebook_summary_path(
        resolved_counterpart,
        review_dir=review_dir,
    )
    current_summary = read_feature_pipeline_notebook_summary(
        normalized_backend,
        review_dir=review_dir,
    )
    other_summary = read_feature_pipeline_notebook_summary(
        resolved_counterpart,
        review_dir=review_dir,
    )

    comparison_rows: list[dict[str, Any]] = []
    mismatched_fields: list[str] = []
    missing_in_current: list[str] = []
    missing_in_counterpart: list[str] = []

    for field in stable_fields:
        current_present = field in current_summary
        counterpart_present = field in other_summary
        current_value = current_summary.get(field)
        counterpart_value = other_summary.get(field)
        matches = (
            current_present
            and counterpart_present
            and _values_match(field, current_value, counterpart_value)
        )
        if not current_present:
            missing_in_current.append(field)
        if not counterpart_present:
            missing_in_counterpart.append(field)
        if not matches:
            mismatched_fields.append(field)

        comparison_rows.append(
            {
                "field": field,
                "current": current_value,
                "counterpart": counterpart_value,
                "present_in_current": current_present,
                "present_in_counterpart": counterpart_present,
                "matches": matches,
            }
        )

    all_match = not mismatched_fields
    expected_differences = [
        {
            "field": field,
            "current": current_summary.get(field),
            "counterpart": other_summary.get(field),
        }
        for field in _EXPECTED_DIFFERENCE_FIELDS
        if field in current_summary or field in other_summary
    ]

    return {
        "status": "pass" if all_match else "fail",
        "backend": normalized_backend,
        "summary_path": str(current_path),
        "counterpart_backend": resolved_counterpart,
        "counterpart_summary_path": str(other_path),
        "stable_fields": list(stable_fields),
        "all_match": all_match,
        "mismatched_fields": mismatched_fields,
        "missing_in_current": missing_in_current,
        "missing_in_counterpart": missing_in_counterpart,
        "comparison": comparison_rows,
        "expected_differences": expected_differences,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    compare_parser = subparsers.add_parser(
        "compare",
        help="Compare backend-tagged notebook review summaries for stable parity.",
    )
    compare_parser.add_argument("--backend", required=True, choices=_VALID_BACKENDS)
    compare_parser.add_argument("--counterpart-backend", default=None)
    compare_parser.add_argument("--review-dir", default=None)
    return parser


def run_cli(argv: Sequence[str] | None = None) -> int:
    """Run the notebook review parity CLI and return its exit code."""
    args = _build_parser().parse_args(argv)

    if args.command != "compare":
        raise ValueError(f"Unsupported command: {args.command}")

    try:
        report = compare_feature_pipeline_notebook_summaries(
            args.backend,
            counterpart_backend_name=args.counterpart_backend,
            review_dir=args.review_dir,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["all_match"] else 1


def main() -> None:
    raise SystemExit(run_cli())


__all__ = [
    "FEATURE_PIPELINE_NOTEBOOK_STABLE_FIELDS",
    "compare_feature_pipeline_notebook_summaries",
    "counterpart_backend",
    "feature_pipeline_notebook_review_dir",
    "feature_pipeline_notebook_summary_path",
    "main",
    "read_feature_pipeline_notebook_summary",
    "run_cli",
]


if __name__ == "__main__":
    main()
