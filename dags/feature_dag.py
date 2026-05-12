"""Airflow DAG for the local feature pipeline."""

from __future__ import annotations

from datetime import datetime
import os

try:
    from airflow.providers.standard.operators.python import (
        PythonOperator,
        ShortCircuitOperator,
    )
    from airflow.providers.standard.operators.trigger_dagrun import (
        TriggerDagRunOperator,
    )
    from airflow.sdk import DAG
except ModuleNotFoundError:  # pragma: no cover - Airflow is container-only
    dag = None
else:
    from foehncast.orchestration import (
        engineer_feature_pipeline_context,
        fetch_feature_pipeline_context,
        resolve_auto_retraining_mode,
        resolve_airflow_schedule,
        store_feature_pipeline_job_context,
        should_auto_retrain,
        validate_feature_pipeline_context,
    )

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
            "slices, and optionally trigger the separate retraining DAG."
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

            trigger_training_pipeline = TriggerDagRunOperator(
                task_id="trigger_training_pipeline",
                trigger_dag_id="training_pipeline",
                conf={
                    "dataset": feature_dataset,
                    "source_dag_id": "feature_pipeline",
                    "source_run_id": "{{ run_id }}",
                },
                wait_for_completion=False,
            )

            (
                fetch_feature_inputs
                >> engineer_feature_set
                >> validate_feature_set
                >> store_feature_set
                >> retraining_gate
                >> trigger_training_pipeline
            )

        else:
            (
                fetch_feature_inputs
                >> engineer_feature_set
                >> validate_feature_set
                >> store_feature_set
            )
