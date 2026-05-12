"""Airflow DAG for local model training, evaluation, and registration."""

from __future__ import annotations

from datetime import datetime
import os

try:
    from airflow.providers.standard.operators.python import PythonOperator
    from airflow.sdk import Asset, DAG
except ModuleNotFoundError:  # pragma: no cover - Airflow is container-only
    dag = None
else:
    from foehncast.airflow_assets import (
        curated_feature_store_asset_uri,
        mlflow_evaluation_asset_uri,
        mlflow_registry_asset_uri,
        mlflow_training_run_asset_uri,
        training_request_asset_uri,
    )
    from foehncast.orchestration import (
        evaluate_training_run,
        register_training_run,
        run_training_pipeline_step,
    )

    training_dataset = (
        os.getenv("AIRFLOW_TRAINING_DATASET")
        or os.getenv("AIRFLOW_FEATURE_DATASET")
        or "train"
    ).strip() or "train"
    training_dataset_template = (
        "{{ dag_run.conf.get('dataset') if dag_run and dag_run.conf and "
        "dag_run.conf.get('dataset') else params.dataset }}"
    )
    registration_stage_template = (
        "{{ dag_run.conf.get('stage') if dag_run and dag_run.conf and "
        "dag_run.conf.get('stage') else ('Production' if dag_run and "
        "dag_run.run_type == 'asset_triggered' else 'Candidate') }}"
    )
    curated_feature_store_asset = Asset(
        name=f"{training_dataset}_curated_feature_store",
        uri=curated_feature_store_asset_uri(training_dataset),
    )
    training_request_asset = Asset(
        name=f"{training_dataset}_production_training_request",
        uri=training_request_asset_uri(training_dataset, stage="production"),
    )
    training_run_asset = Asset(
        name=f"{training_dataset}_mlflow_training_run",
        uri=mlflow_training_run_asset_uri(training_dataset),
    )
    evaluation_asset = Asset(
        name=f"{training_dataset}_mlflow_evaluation_report",
        uri=mlflow_evaluation_asset_uri(training_dataset),
    )
    model_registry_asset = Asset(
        name="foehncast_mlflow_model_registry",
        uri=mlflow_registry_asset_uri(),
    )

    with DAG(
        dag_id="training_pipeline",
        description=(
            "Train the model, log evaluation outputs, and register the new version "
            "when started manually or when a training-request asset arrives from "
            "the feature DAG."
        ),
        start_date=datetime(2024, 1, 1),
        schedule=[training_request_asset],
        catchup=False,
        is_paused_upon_creation=False,
        params={"dataset": training_dataset},
        tags=["foehncast", "training"],
    ) as dag:
        train_model = PythonOperator(
            task_id="train_model",
            python_callable=run_training_pipeline_step,
            inlets=[curated_feature_store_asset, training_request_asset],
            outlets=[training_run_asset],
            op_kwargs={
                "dataset": training_dataset_template,
                "requested_stage": registration_stage_template,
            },
        )

        evaluate_model_task = PythonOperator(
            task_id="evaluate_model",
            python_callable=evaluate_training_run,
            inlets=[training_run_asset],
            outlets=[evaluation_asset],
            op_args=[train_model.output],
            op_kwargs={
                "dataset": training_dataset_template,
                "requested_stage": registration_stage_template,
            },
        )

        register_model_task = PythonOperator(
            task_id="register_model",
            python_callable=register_training_run,
            inlets=[training_run_asset, evaluation_asset],
            outlets=[model_registry_asset],
            op_args=[train_model.output],
            op_kwargs={
                "stage": registration_stage_template,
                "dataset": training_dataset_template,
            },
        )

        train_model >> evaluate_model_task >> register_model_task
