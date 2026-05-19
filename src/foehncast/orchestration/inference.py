"""Inference pipeline orchestration: scheduled prediction runs."""

from __future__ import annotations

from typing import Any


def run_inference_pipeline_step() -> dict[str, Any]:
    """Run inference for all configured spots and write the prediction log.

    Thin wrapper around :func:`foehncast.inference_pipeline.predict.run_inference`
    for backward compatibility with the Airflow DAG and existing tests.
    """
    from foehncast.inference_pipeline.predict import run_inference

    return run_inference(endpoint="scheduled")
