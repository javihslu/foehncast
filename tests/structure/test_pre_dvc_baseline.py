"""Pre-DVC FTI baseline tests.

Validate that the feature-to-training-to-inference pipeline stages, monitoring
contracts, and DAG asset linkage are stable enough for DVC to wrap without
redefining the stage boundaries or monitoring signals.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from foehncast.airflow_assets import (
    curated_feature_store_asset_uri,
    training_request_asset_uri,
)
from foehncast.monitoring.pipeline_contracts import (
    FEATURE_PIPELINE_METRIC_CONTRACT,
    TRAINING_PIPELINE_METRIC_CONTRACT,
)
from foehncast.pipeline_stage_tracking import (
    FEATURE_PIPELINE_STAGES,
    TRAINING_PIPELINE_STAGES,
)

from tests.repo_helpers import read_repo_text


# 1. Stage boundary stability


@pytest.mark.parametrize(
    ("stages", "expected"),
    [
        (FEATURE_PIPELINE_STAGES, ("fetch", "engineer", "validate", "store")),
        (TRAINING_PIPELINE_STAGES, ("train", "evaluate", "register")),
    ],
    ids=["feature", "training"],
)
def test_pipeline_stages_are_ordered_and_complete(
    stages: tuple[str, ...], expected: tuple[str, ...]
) -> None:
    """DVC stages will mirror these; any change breaks the DVC pipeline."""
    assert stages == expected


# 2. Monitoring contracts cover every pipeline stage


@pytest.mark.parametrize(
    ("stages", "contract", "stage_map"),
    [
        (
            FEATURE_PIPELINE_STAGES,
            FEATURE_PIPELINE_METRIC_CONTRACT,
            {
                "fetch": "ingest",
                "engineer": "engineering",
                "validate": "validation",
                "store": "storage",
            },
        ),
        (
            TRAINING_PIPELINE_STAGES,
            TRAINING_PIPELINE_METRIC_CONTRACT,
            {"train": "train", "evaluate": "evaluation", "register": "registration"},
        ),
    ],
    ids=["feature", "training"],
)
def test_monitoring_contract_covers_all_stages(
    stages: tuple[str, ...], contract: dict, stage_map: dict[str, str]
) -> None:
    """Each pipeline stage must have a monitoring contract section."""
    for stage in stages:
        contract_key = stage_map.get(stage, stage)
        assert contract_key in contract, (
            f"Stage '{stage}' has no monitoring contract section "
            f"(expected key '{contract_key}')"
        )


@pytest.mark.parametrize(
    "contract",
    [FEATURE_PIPELINE_METRIC_CONTRACT, TRAINING_PIPELINE_METRIC_CONTRACT],
    ids=["feature", "training"],
)
def test_monitoring_run_contract_tracks_stage_durations_and_failures(
    contract: dict,
) -> None:
    """Run-level summary must include stage tracking for duration and failure counts."""
    run_fields = contract["run"]
    assert "stage_durations_seconds" in run_fields
    assert "stage_failure_counts" in run_fields


# 3. Feature→Training asset linkage


def test_feature_dag_training_request_asset_matches_training_dag_schedule() -> None:
    """The feature DAG outlet and training DAG schedule must use the same URI."""
    dataset = "train"
    feature_outlet_uri = training_request_asset_uri(dataset, stage="Production")
    # The training DAG normalises stage to lowercase.
    training_schedule_uri = training_request_asset_uri(dataset, stage="production")
    assert feature_outlet_uri == training_schedule_uri


def test_curated_feature_store_asset_uri_is_stable() -> None:
    """DVC will consume curated data at this URI; changes break the contract."""
    assert curated_feature_store_asset_uri("train") == (
        "x-foehncast://feature-pipeline/curated/train"
    )


# 4. Local evaluator smoke covers the full FTI path


def test_bootstrap_local_runs_feature_then_waits_for_training() -> None:
    """The smoke must prove feature→training before DVC can wrap them."""
    script = read_repo_text("scripts/bootstrap-local.sh")

    assert "feature_pipeline" in script
    assert "training_pipeline" in script

    feature_pos = script.index("feature_pipeline")
    training_pos = script.index("training_pipeline")
    assert feature_pos < training_pos, (
        "bootstrap-local must run the feature pipeline before waiting for training"
    )


def test_bootstrap_local_verifies_monitoring_surfaces() -> None:
    """The smoke must verify app metrics."""
    script = read_repo_text("scripts/bootstrap-local.sh")

    assert "APP_METRICS_URL" in script


def test_bootstrap_local_verifies_feast_online_features() -> None:
    """The smoke must confirm Feast serving state before declaring success."""
    script = read_repo_text("scripts/bootstrap-local.sh")

    assert "prepare-feast-local.sh" in script
    assert "/features/online" in script


def test_bootstrap_local_prepares_monitoring_state_dirs() -> None:
    """Runtime paths include the monitoring state directory."""
    script = read_repo_text("scripts/bootstrap-local.sh")
    assert ".state/monitoring" in script


# 5. CI contract enforces local evaluator smoke


def test_ci_compose_job_runs_smoke_after_build() -> None:
    """CI must run the local evaluator smoke — DVC depends on this gate."""
    from tests.repo_helpers import read_workflow_yaml

    workflow = read_workflow_yaml(".github/workflows/ci.yml")
    steps = workflow["jobs"]["compose"]["steps"]
    runs = [step["run"] for step in steps if "run" in step]

    assert "make smoke-local-evaluator" in runs


# 6. Hosted operator lane exposes equivalent stage evidence


def test_hosted_dag_bundle_contains_feature_and_training_dags() -> None:
    """The hosted docs still point at the same DAG sources as the local evaluator."""
    feature_dag = Path("dags/feature_dag.py")
    training_dag = Path("dags/training_dag.py")

    assert (
        feature_dag.exists()
        or (Path(__file__).resolve().parent.parent.parent / feature_dag).exists()
    )
    assert (
        training_dag.exists()
        or (Path(__file__).resolve().parent.parent.parent / training_dag).exists()
    )


def test_hosted_operator_terraform_exposes_cloud_run_contract() -> None:
    """Terraform must declare Cloud Run resources for the hosted lane."""
    terraform_main = read_repo_text("terraform/main.tf")

    assert (
        "google_cloud_run_v2_service" in terraform_main
        or "cloud_run" in terraform_main.lower()
    )


# 7. No DVC artefacts exist yet (pre-condition)


def test_dvc_pipeline_definition_exists() -> None:
    """DVC stages are now defined; validate the pipeline file is present."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    assert (repo_root / "dvc.yaml").exists(), "dvc.yaml must exist"
    assert (repo_root / ".dvc").is_dir(), ".dvc/ must exist"


# 8. Stage-to-DAG task mapping consistency


@pytest.mark.parametrize(
    ("dag_file", "task_map"),
    [
        (
            "dags/feature_dag.py",
            {
                "fetch": "fetch_feature_inputs",
                "engineer": "engineer_feature_set",
                "validate": "validate_feature_set",
                "store": "store_feature_set",
            },
        ),
        (
            "dags/training_dag.py",
            {
                "train": "train_model",
                "evaluate": "evaluate_model",
                "register": "register_model",
            },
        ),
    ],
    ids=["feature", "training"],
)
def test_dag_has_tasks_covering_all_stages(
    dag_file: str, task_map: dict[str, str]
) -> None:
    """Each pipeline stage must have a corresponding Airflow task."""
    dag_source = read_repo_text(dag_file)

    for stage, task_fragment in task_map.items():
        assert task_fragment in dag_source, (
            f"DAG is missing a task for stage '{stage}' "
            f"(expected '{task_fragment}' in {dag_file})"
        )
