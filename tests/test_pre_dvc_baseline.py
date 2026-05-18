"""Pre-DVC FTI baseline tests.

Validate that the feature-to-training-to-inference pipeline stages, monitoring
contracts, and DAG asset linkage are stable enough for DVC to wrap without
redefining the stage boundaries or monitoring signals.
"""

from __future__ import annotations

from pathlib import Path

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


# ---------------------------------------------------------------------------
# 1. Stage boundary stability
# ---------------------------------------------------------------------------


def test_feature_pipeline_stages_are_ordered_and_complete() -> None:
    """DVC stages will mirror these; any change breaks the DVC pipeline."""
    assert FEATURE_PIPELINE_STAGES == ("fetch", "engineer", "validate", "store")


def test_training_pipeline_stages_are_ordered_and_complete() -> None:
    """DVC stages will mirror these; any change breaks the DVC pipeline."""
    assert TRAINING_PIPELINE_STAGES == ("train", "evaluate", "register")


# ---------------------------------------------------------------------------
# 2. Monitoring contracts cover every pipeline stage
# ---------------------------------------------------------------------------


def test_feature_monitoring_contract_covers_all_stages() -> None:
    """Each feature-pipeline stage must have a monitoring contract section."""
    stage_to_contract_key = {
        "fetch": "ingest",
        "engineer": "engineering",
        "validate": "validation",
        "store": "storage",
    }
    for stage in FEATURE_PIPELINE_STAGES:
        contract_key = stage_to_contract_key.get(stage, stage)
        assert contract_key in FEATURE_PIPELINE_METRIC_CONTRACT, (
            f"Feature stage '{stage}' has no monitoring contract section "
            f"(expected key '{contract_key}')"
        )


def test_training_monitoring_contract_covers_all_stages() -> None:
    """Each training-pipeline stage must have a monitoring contract section."""
    stage_to_contract_key = {
        "train": "train",
        "evaluate": "evaluation",
        "register": "registration",
    }
    for stage in TRAINING_PIPELINE_STAGES:
        contract_key = stage_to_contract_key.get(stage, stage)
        assert contract_key in TRAINING_PIPELINE_METRIC_CONTRACT, (
            f"Training stage '{stage}' has no monitoring contract section "
            f"(expected key '{contract_key}')"
        )


def test_feature_monitoring_run_contract_tracks_stage_durations_and_failures() -> None:
    """Run-level summary must include stage tracking for duration and failure counts."""
    run_fields = FEATURE_PIPELINE_METRIC_CONTRACT["run"]
    assert "stage_durations_seconds" in run_fields
    assert "stage_failure_counts" in run_fields


def test_training_monitoring_run_contract_tracks_stage_durations_and_failures() -> None:
    """Run-level summary must include stage tracking for duration and failure counts."""
    run_fields = TRAINING_PIPELINE_METRIC_CONTRACT["run"]
    assert "stage_durations_seconds" in run_fields
    assert "stage_failure_counts" in run_fields


# ---------------------------------------------------------------------------
# 3. Feature→Training asset linkage
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# 4. Local evaluator smoke covers the full FTI path
# ---------------------------------------------------------------------------


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
    """The smoke must verify Grafana provisioning and app metrics."""
    script = read_repo_text("scripts/bootstrap-local.sh")

    assert "verify_grafana_provisioning" in script
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


# ---------------------------------------------------------------------------
# 5. CI contract enforces local evaluator smoke
# ---------------------------------------------------------------------------


def test_ci_compose_job_runs_smoke_after_build() -> None:
    """CI must run the local evaluator smoke — DVC depends on this gate."""
    from tests.repo_helpers import read_workflow_yaml

    workflow = read_workflow_yaml(".github/workflows/ci.yml")
    steps = workflow["jobs"]["compose"]["steps"]
    runs = [step["run"] for step in steps if "run" in step]

    assert "make smoke-local-evaluator" in runs


# ---------------------------------------------------------------------------
# 6. Hosted operator lane exposes equivalent stage evidence
# ---------------------------------------------------------------------------


def test_hosted_dag_bundle_contains_feature_and_training_dags() -> None:
    """Cloud Composer receives the same DAG files that the local evaluator uses."""
    feature_dag = Path("dags/feature_dag.py")
    training_dag = Path("dags/training_dag.py")

    assert (
        feature_dag.exists()
        or (Path(__file__).resolve().parent.parent / feature_dag).exists()
    )
    assert (
        training_dag.exists()
        or (Path(__file__).resolve().parent.parent / training_dag).exists()
    )


def test_composer_bundle_includes_pipeline_source_package() -> None:
    """The Composer DAG bundle must include the foehncast source package."""
    from foehncast.composer_bundle import composer_bundle_mappings

    mappings = composer_bundle_mappings()
    sources = [m["source"] for m in mappings]
    assert "src/foehncast" in sources, (
        "Composer bundle must include src/foehncast so pipeline_stage_tracking "
        "and monitoring contracts are available to Cloud Composer DAGs"
    )


def test_hosted_operator_terraform_exposes_cloud_run_and_composer_contract() -> None:
    """Terraform must declare Cloud Run and Composer resources for the hosted lane."""
    terraform_main = read_repo_text("terraform/main.tf")

    assert (
        "google_cloud_run_v2_service" in terraform_main
        or "cloud_run" in terraform_main.lower()
    )
    assert (
        "google_cloud_composer" in terraform_main
        or "composer" in terraform_main.lower()
    )


# ---------------------------------------------------------------------------
# 7. No DVC artefacts exist yet (pre-condition)
# ---------------------------------------------------------------------------


def test_dvc_pipeline_definition_exists() -> None:
    """DVC stages are now defined; validate the pipeline file is present."""
    repo_root = Path(__file__).resolve().parent.parent
    assert (repo_root / "dvc.yaml").exists(), "dvc.yaml must exist"
    assert (repo_root / ".dvc").is_dir(), ".dvc/ must exist"


# ---------------------------------------------------------------------------
# 8. Stage-to-DAG task mapping consistency
# ---------------------------------------------------------------------------


def test_feature_dag_has_tasks_covering_all_stages() -> None:
    """Each feature-pipeline stage must have a corresponding Airflow task."""
    dag_source = read_repo_text("dags/feature_dag.py")

    expected_task_fragments = {
        "fetch": "fetch_feature_inputs",
        "engineer": "engineer_feature_set",
        "validate": "validate_feature_set",
        "store": "store_feature_set",
    }
    for stage, task_fragment in expected_task_fragments.items():
        assert task_fragment in dag_source, (
            f"Feature DAG is missing a task for stage '{stage}' "
            f"(expected '{task_fragment}' in feature_dag.py)"
        )


def test_training_dag_has_tasks_covering_all_stages() -> None:
    """Each training-pipeline stage must have a corresponding Airflow task."""
    dag_source = read_repo_text("dags/training_dag.py")

    expected_task_fragments = {
        "train": "train_model",
        "evaluate": "evaluate_model",
        "register": "register_model",
    }
    for stage, task_fragment in expected_task_fragments.items():
        assert task_fragment in dag_source, (
            f"Training DAG is missing a task for stage '{stage}' "
            f"(expected '{task_fragment}' in training_dag.py)"
        )
