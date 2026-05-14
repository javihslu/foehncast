"""Promote validated model versions to the live serving alias."""

from __future__ import annotations

import argparse

import mlflow

from foehncast.config import get_mlflow_config, get_mlflow_tracking_uri
from foehncast.training_pipeline.register import (
    _configured_mlflow_client,
    _normalized_alias,
    _normalized_version,
    _resolved_model_name,
    promote_model,
)


def resolve_model_version_by_alias(alias: str, model_name: str | None = None) -> str:
    """Return the registered model version currently assigned to an alias."""
    normalized_alias = _normalized_alias(alias)

    mlflow_config = get_mlflow_config()
    resolved_model_name = _resolved_model_name(model_name, mlflow_config)
    client = _configured_mlflow_client(mlflow, get_mlflow_tracking_uri())
    model_version = client.get_model_version_by_alias(
        resolved_model_name, normalized_alias
    )
    return str(model_version.version)


def promote_model_version(
    version: str | int, *, stage: str = "Production", model_name: str | None = None
) -> str:
    """Assign the target stage alias to an explicit registered model version."""
    normalized_version = _normalized_version(version)

    promote_model(model_name, normalized_version, stage=stage)
    return normalized_version


def promote_model_alias(
    source_alias: str = "candidate",
    *,
    stage: str = "Production",
    model_name: str | None = None,
) -> str:
    """Promote the version currently behind a source alias."""
    version = resolve_model_version_by_alias(source_alias, model_name=model_name)
    return promote_model_version(version, stage=stage, model_name=model_name)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-name", default=None)
    parser.add_argument("--source-alias", default="candidate")
    parser.add_argument("--version", default=None)
    parser.add_argument("--target-stage", default="Production")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if args.version is not None:
        promoted_version = promote_model_version(
            args.version,
            stage=args.target_stage,
            model_name=args.model_name,
        )
    else:
        promoted_version = promote_model_alias(
            args.source_alias,
            stage=args.target_stage,
            model_name=args.model_name,
        )

    print(promoted_version)


if __name__ == "__main__":
    main()
