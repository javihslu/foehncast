"""Airflow DAG for local model training, evaluation, and registration."""

from __future__ import annotations

from datetime import datetime

try:
    from airflow import DAG
    from airflow.operators.python import PythonOperator
except ModuleNotFoundError:  # pragma: no cover - Airflow is container-only
    dag = None
else:
    from foehncast.orchestration import evaluate_training_run, register_training_run
    from foehncast.training_pipeline.train import run_training_pipeline

    with DAG(
        dag_id="training_pipeline",
        description="Train the model, log evaluation outputs, and register the new version.",
        start_date=datetime(2024, 1, 1),
        schedule=None,
        catchup=False,
        tags=["foehncast", "training"],
    ) as dag:
        train_model = PythonOperator(
            task_id="train_model",
            python_callable=run_training_pipeline,
        )

        evaluate_model_task = PythonOperator(
            task_id="evaluate_model",
            python_callable=evaluate_training_run,
            op_args=[train_model.output],
        )

        register_model_task = PythonOperator(
            task_id="register_model",
            python_callable=register_training_run,
            op_args=[train_model.output],
        )

        train_model >> evaluate_model_task >> register_model_task
