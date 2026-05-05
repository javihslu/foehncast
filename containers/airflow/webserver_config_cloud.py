"""Shared Airflow webserver settings for the online stack."""

from flask_appbuilder.const import AUTH_DB


AUTH_TYPE = AUTH_DB
AUTH_ROLE_PUBLIC = "Public"
