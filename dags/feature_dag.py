"""Airflow DAG for the local feature pipeline."""

from __future__ import annotations

from datetime import datetime

try:
    from airflow.providers.standard.operators.empty import EmptyOperator
    from airflow.providers.standard.operators.python import (
        PythonOperator,
        ShortCircuitOperator,
    )
    from airflow.sdk import Asset, DAG
except ModuleNotFoundError:  # pragma: no cover - Airflow is container-only
    dag = None
else:
    from foehncast.airflow_assets import (
        curated_feature_store_asset_uri,
        feast_feature_store_asset_uri,
        training_request_asset_uri,
    )
    from foehncast.env import env_value
    from foehncast.feature_pipeline.feast import prepare_feature_store
    from foehncast.orchestration import (
        engineer_feature_pipeline_context,
        fetch_feature_pipeline_context,
        resolve_auto_retraining_mode,
        resolve_airflow_schedule,
        store_feature_pipeline_job_context,
        should_auto_retrain,
        validate_feature_pipeline_context,
    )

    feature_dataset = env_value("AIRFLOW_FEATURE_DATASET") or "train"
    feature_schedule = resolve_airflow_schedule(
        env_value("AIRFLOW_FEATURE_SCHEDULE"),
        default="0 */6 * * *",
    )
    auto_retrain_mode = resolve_auto_retraining_mode(
        env_value("AIRFLOW_AUTO_RETRAIN_MODE"),
        default="always",
    )
    training_request_stage = "Production"
    curated_feature_store_asset = Asset(
        name=f"{feature_dataset}_curated_feature_store",
        uri=curated_feature_store_asset_uri(feature_dataset),
    )
    feast_feature_store_asset = Asset(
        name=f"{feature_dataset}_feast_feature_store",
        uri=feast_feature_store_asset_uri(feature_dataset),
    )
    training_request_asset = Asset(
        name=f"{feature_dataset}_production_training_request",
        uri=training_request_asset_uri(
            feature_dataset,
            stage=training_request_stage,
        ),
    )

    with DAG(
        dag_id="feature_pipeline",
        description=(
            "Fetch forecasts, engineer features, validate them, persist curated "
            "slices, sync the local Feast store, and optionally publish a "
            "retraining asset request for the separate training DAG."
        ),
        start_date=datetime(2024, 1, 1),
        schedule=feature_schedule,
        catchup=False,
        is_paused_upon_creation=False,
        tags=["foehncast", "feature"],
    ) as dag:
        fetch_feature_inputs = PythonOperator(
            task_id="fetch_feature_inputs",
            python_callable=fetch_feature_pipeline_context,
            op_kwargs={"dataset": feature_dataset, "run_key": "{{ run_id }}"},
        )

        engineer_feature_set = PythonOperator(
            task_id="engineer_feature_set",
            python_callable=engineer_feature_pipeline_context,
            op_args=[fetch_feature_inputs.output],
        )

        validate_feature_set = PythonOperator(
            task_id="validate_feature_set",
            python_callable=validate_feature_pipeline_context,
            op_args=[engineer_feature_set.output],
        )

        store_feature_set = PythonOperator(
            task_id="store_feature_set",
            python_callable=store_feature_pipeline_job_context,
            op_args=[validate_feature_set.output],
            op_kwargs={
                "auto_retraining_mode": auto_retrain_mode,
                "training_request_stage": training_request_stage,
            },
        )

        prepare_feast_feature_store = PythonOperator(
            task_id="prepare_feast_feature_store",
            python_callable=prepare_feature_store,
            op_kwargs={"dataset": feature_dataset},
            outlets=[curated_feature_store_asset, feast_feature_store_asset],
        )

        if auto_retrain_mode is not None:
            retraining_gate = ShortCircuitOperator(
                task_id="check_retraining_trigger",
                python_callable=should_auto_retrain,
                op_kwargs={
                    "feature_result": store_feature_set.output,
                    "mode": auto_retrain_mode,
                },
            )

            publish_training_request = EmptyOperator(
                task_id="publish_training_request",
                outlets=[training_request_asset],
            )

            (
                fetch_feature_inputs
                >> engineer_feature_set
                >> validate_feature_set
                >> store_feature_set
                >> prepare_feast_feature_store
                >> retraining_gate
                >> publish_training_request
            )

        else:
            (
                fetch_feature_inputs
                >> engineer_feature_set
                >> validate_feature_set
                >> store_feature_set
                >> prepare_feast_feature_store
            )
