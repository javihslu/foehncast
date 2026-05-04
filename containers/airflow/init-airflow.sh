#!/bin/sh

# Set up Airflow so the other Airflow services can start after this container
# is ready.

set -eu

airflow_home="/workspace/airflow"
marker_file="${AIRFLOW_INIT_MARKER:-$airflow_home/.init-complete}"
admin_username="${AIRFLOW_ADMIN_USERNAME:-admin}"
admin_firstname="${AIRFLOW_ADMIN_FIRSTNAME:-Admin}"
admin_lastname="${AIRFLOW_ADMIN_LASTNAME:-User}"
admin_role="${AIRFLOW_ADMIN_ROLE:-Admin}"
admin_email="${AIRFLOW_ADMIN_EMAIL:-admin@example.com}"
admin_password="${AIRFLOW_ADMIN_PASSWORD:-admin}"

rm -f "$marker_file"
mkdir -p "$airflow_home/logs" "$airflow_home/reports"
rm -f "$airflow_home"/*.pid

airflow db migrate
airflow users create \
  --username "$admin_username" \
  --firstname "$admin_firstname" \
  --lastname "$admin_lastname" \
  --role "$admin_role" \
  --email "$admin_email" \
  --password "$admin_password" || true

touch "$marker_file"
exec tail -f /dev/null
