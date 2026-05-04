"""Airflow DAG for the local feature pipeline."""

from __future__ import annotations

from datetime import datetime

try:
    from airflow import DAG
    from airflow.operators.python import PythonOperator
except ModuleNotFoundError:  # pragma: no cover - Airflow is container-only
    dag = None
else:
    from foehncast.orchestration import run_feature_pipeline

    with DAG(
        dag_id="feature_pipeline",
        description="Fetch forecasts, engineer features, validate them, and store them.",
        start_date=datetime(2024, 1, 1),
        schedule=None,
        catchup=False,
        tags=["foehncast", "feature"],
    ) as dag:
        PythonOperator(
            task_id="run_feature_pipeline",
            python_callable=run_feature_pipeline,
        )
