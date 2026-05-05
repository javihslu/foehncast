"""Airflow DAG for the local feature pipeline."""

from __future__ import annotations

from datetime import datetime
import os

try:
    from airflow import DAG
    from airflow.operators.python import PythonOperator
except ModuleNotFoundError:  # pragma: no cover - Airflow is container-only
    dag = None
else:
    from foehncast.orchestration import (
        resolve_airflow_schedule,
        run_feature_pipeline_job,
    )

    feature_dataset = os.getenv("AIRFLOW_FEATURE_DATASET", "train").strip() or "train"
    feature_schedule = resolve_airflow_schedule(
        os.getenv("AIRFLOW_FEATURE_SCHEDULE"),
        default="0 */6 * * *",
    )

    with DAG(
        dag_id="feature_pipeline",
        description="Fetch forecasts, engineer features, validate them, and store them.",
        start_date=datetime(2024, 1, 1),
        schedule=feature_schedule,
        catchup=False,
        tags=["foehncast", "feature"],
    ) as dag:
        PythonOperator(
            task_id="run_feature_pipeline",
            python_callable=run_feature_pipeline_job,
            op_kwargs={"dataset": feature_dataset},
        )
