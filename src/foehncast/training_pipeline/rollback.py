"""Restore a previously validated model version to the live serving alias."""

from __future__ import annotations

import argparse

from foehncast.training_pipeline.register import assign_model_alias


def rollback_model_version(
    version: str | int,
    *,
    target_alias: str = "champion",
    model_name: str | None = None,
) -> str:
    """Reassign the live alias to an explicit previous model version."""
    normalized_version = str(version).strip()
    if not normalized_version:
        raise ValueError("Model version must be non-empty")

    normalized_alias = target_alias.strip()
    if not normalized_alias:
        raise ValueError("Target alias must be non-empty")

    assign_model_alias(normalized_alias, normalized_version, model_name=model_name)
    return normalized_version


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-name", default=None)
    parser.add_argument("--version", required=True)
    parser.add_argument("--target-alias", default="champion")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    restored_version = rollback_model_version(
        args.version,
        target_alias=args.target_alias,
        model_name=args.model_name,
    )
    print(restored_version)


if __name__ == "__main__":
    main()
