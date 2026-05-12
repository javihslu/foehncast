"""Airflow DAG for local model training, evaluation, and registration."""

from __future__ import annotations

from datetime import datetime
import os

try:
    from airflow.providers.standard.operators.python import PythonOperator
    from airflow.sdk import DAG
except ModuleNotFoundError:  # pragma: no cover - Airflow is container-only
    dag = None
else:
    from foehncast.orchestration import evaluate_training_run, register_training_run
    from foehncast.training_pipeline.train import run_training_pipeline

    training_dataset = os.getenv("AIRFLOW_TRAINING_DATASET", "train").strip() or "train"
    training_dataset_template = (
        "{{ dag_run.conf.get('dataset') if dag_run and dag_run.conf and "
        "dag_run.conf.get('dataset') else params.dataset }}"
    )

    with DAG(
        dag_id="training_pipeline",
        description=(
            "Train the model, log evaluation outputs, and register the new version "
            "when started manually or triggered from the feature DAG."
        ),
        start_date=datetime(2024, 1, 1),
        schedule=None,
        catchup=False,
        is_paused_upon_creation=True,
        params={"dataset": training_dataset},
        tags=["foehncast", "training"],
    ) as dag:
        train_model = PythonOperator(
            task_id="train_model",
            python_callable=run_training_pipeline,
            op_kwargs={"dataset": training_dataset_template},
        )

        evaluate_model_task = PythonOperator(
            task_id="evaluate_model",
            python_callable=evaluate_training_run,
            op_args=[train_model.output],
            op_kwargs={"dataset": training_dataset_template},
        )

        register_model_task = PythonOperator(
            task_id="register_model",
            python_callable=register_training_run,
            op_args=[train_model.output],
        )

        train_model >> evaluate_model_task >> register_model_task
