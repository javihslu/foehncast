"""Local-only Airflow webserver settings."""

from flask_appbuilder.const import AUTH_DB


# Give anonymous localhost users full access to the local Airflow UI.
# Do not reuse this config for shared or public deployments.
AUTH_TYPE = AUTH_DB
AUTH_ROLE_PUBLIC = "Admin"
