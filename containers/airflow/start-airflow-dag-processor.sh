#!/bin/sh

# Start the Airflow DAG processor in its own container.

set -eu

exec airflow dag-processor
