#!/bin/sh

# Set up Airflow so the other Airflow services can start after this container
# is ready.

set -eu

airflow_home="/workspace/airflow"
marker_file="${AIRFLOW_INIT_MARKER:-$airflow_home/.init-complete}"
admin_username="${AIRFLOW_ADMIN_USERNAME:-admin}"
admin_password_file="${AIRFLOW_ADMIN_PASSWORD_FILE:-}"
admin_password="${AIRFLOW_ADMIN_PASSWORD:-admin}"
simple_auth_manager_all_admins="${AIRFLOW__CORE__SIMPLE_AUTH_MANAGER_ALL_ADMINS:-false}"
simple_auth_manager_passwords_file="${AIRFLOW__CORE__SIMPLE_AUTH_MANAGER_PASSWORDS_FILE:-$airflow_home/simple_auth_manager_passwords.json.generated}"

if [ -n "$admin_password_file" ] && [ -f "$admin_password_file" ]; then
  admin_password="$(cat "$admin_password_file")"
fi

rm -f "$marker_file"
mkdir -p "$airflow_home/logs" "$airflow_home/reports"
rm -f "$airflow_home"/*.pid
rm -f "$airflow_home/airflow.cfg" "$airflow_home/webserver_config.py"

simple_auth_manager_all_admins_enabled=false
case "$simple_auth_manager_all_admins" in
  1|true|TRUE|True|yes|YES|Yes)
    simple_auth_manager_all_admins_enabled=true
    ;;
esac

if [ "$simple_auth_manager_all_admins_enabled" != true ] && [ -n "$admin_username" ] && [ -n "$admin_password" ]; then
  mkdir -p "$(dirname "$simple_auth_manager_passwords_file")"
  printf '{"%s":"%s"}\n' "$admin_username" "$admin_password" > "$simple_auth_manager_passwords_file"
  chmod 600 "$simple_auth_manager_passwords_file"
fi

airflow db migrate

touch "$marker_file"
exec tail -f /dev/null
