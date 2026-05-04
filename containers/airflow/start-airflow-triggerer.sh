#!/bin/sh

# Start the Airflow triggerer in its own container.

set -eu

exec airflow triggerer
