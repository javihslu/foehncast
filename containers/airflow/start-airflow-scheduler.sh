#!/bin/sh

# Remove an old pid file, then start the Airflow scheduler.

set -eu

airflow_home="/workspace/airflow"

rm -f "$airflow_home/airflow-scheduler.pid"
exec airflow scheduler
