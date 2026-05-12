"""Airflow DAG for the local feature pipeline."""

from __future__ import annotations

from datetime import datetime
import os

try:
    from airflow.providers.standard.operators.python import (
        PythonOperator,
        ShortCircuitOperator,
    )
    from airflow.sdk import DAG
except ModuleNotFoundError:  # pragma: no cover - Airflow is container-only
    dag = None
else:
    from foehncast.orchestration import (
        engineer_feature_pipeline_context,
        evaluate_training_run,
        fetch_feature_pipeline_context,
        register_training_run,
        resolve_auto_retraining_mode,
        resolve_airflow_schedule,
        store_feature_pipeline_job_context,
        should_auto_retrain,
        validate_feature_pipeline_context,
    )
    from foehncast.training_pipeline.train import run_training_pipeline

    feature_dataset = os.getenv("AIRFLOW_FEATURE_DATASET", "train").strip() or "train"
    feature_schedule = resolve_airflow_schedule(
        os.getenv("AIRFLOW_FEATURE_SCHEDULE"),
        default="0 */6 * * *",
    )
    auto_retrain_mode = resolve_auto_retraining_mode(
        os.getenv("AIRFLOW_AUTO_RETRAIN_MODE"),
        default="always",
    )

    with DAG(
        dag_id="feature_pipeline",
        description=(
            "Fetch forecasts, engineer features, validate them, persist curated "
            "slices, and optionally continue into retraining."
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

            train_model = PythonOperator(
                task_id="train_model",
                python_callable=run_training_pipeline,
                op_kwargs={"dataset": feature_dataset},
            )

            evaluate_model_task = PythonOperator(
                task_id="evaluate_model",
                python_callable=evaluate_training_run,
                op_args=[train_model.output],
                op_kwargs={"dataset": feature_dataset},
            )

            register_model_task = PythonOperator(
                task_id="register_model",
                python_callable=register_training_run,
                op_args=[train_model.output],
            )

            (
                fetch_feature_inputs
                >> engineer_feature_set
                >> validate_feature_set
                >> store_feature_set
                >> retraining_gate
                >> train_model
                >> evaluate_model_task
                >> register_model_task
            )

        else:
            (
                fetch_feature_inputs
                >> engineer_feature_set
                >> validate_feature_set
                >> store_feature_set
            )
