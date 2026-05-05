"""Data quality checks on curated feature rows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from foehncast.config import get_validation_config


@dataclass
class ValidationResult:
    """Structured validation outcome for one spot dataset."""

    spot_id: str
    schema_valid: bool
    completeness_valid: bool
    range_valid: bool
    missing_columns: list[str]
    null_fractions: dict[str, float]
    range_violations: pd.DataFrame

    @property
    def is_valid(self) -> bool:
        return self.schema_valid and self.completeness_valid and self.range_valid


def _missing_columns(df: pd.DataFrame, expected_columns: list[str]) -> list[str]:
    return [column for column in expected_columns if column not in df.columns]


def _null_fractions(df: pd.DataFrame) -> dict[str, float]:
    if df.empty:
        return {column: 0.0 for column in df.columns}
    return df.isna().mean().to_dict()


def validate_schema(df: pd.DataFrame, expected_columns: list[str]) -> bool:
    """Check that all expected columns are present."""
    return not _missing_columns(df, expected_columns)


def validate_ranges(
    df: pd.DataFrame, range_config: dict[str, dict[str, float]]
) -> pd.DataFrame:
    """Return all values that fall outside the configured numeric bounds."""
    violations: list[dict[str, Any]] = []

    for column, bounds in range_config.items():
        if column not in df.columns:
            continue

        series = df[column]
        lower = bounds.get("min")
        upper = bounds.get("max")
        mask = pd.Series(False, index=series.index)

        if lower is not None:
            mask |= series < lower
        if upper is not None:
            mask |= series > upper

        for index, value in series[mask].items():
            violations.append(
                {
                    "column": column,
                    "index": index,
                    "value": value,
                    "min": lower,
                    "max": upper,
                }
            )

    return pd.DataFrame(violations, columns=["column", "index", "value", "min", "max"])


def validate_completeness(df: pd.DataFrame, max_null_pct: float = 0.1) -> bool:
    """Check that no column exceeds the configured null threshold."""
    return all(
        null_fraction <= max_null_pct for null_fraction in _null_fractions(df).values()
    )


def run_validation(df: pd.DataFrame, spot_id: str) -> ValidationResult:
    """Run schema, completeness, and range validation for one curated spot dataset."""
    validation_config = get_validation_config()
    expected_columns = validation_config["required_columns"]
    missing_columns = _missing_columns(df, expected_columns)
    null_fractions = _null_fractions(df)
    range_violations = validate_ranges(df, validation_config["ranges"])

    return ValidationResult(
        spot_id=spot_id,
        schema_valid=not missing_columns,
        completeness_valid=validate_completeness(
            df, validation_config["completeness"]["max_null_pct"]
        ),
        range_valid=range_violations.empty,
        missing_columns=missing_columns,
        null_fractions=null_fractions,
        range_violations=range_violations,
    )
