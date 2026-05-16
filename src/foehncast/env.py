"""Small helpers for reading environment bindings consistently."""

from __future__ import annotations

from functools import lru_cache
import importlib
import os


_SECRET_REF_PREFIX = "sm://"
_DEFAULT_SECRET_VERSION = "latest"
_DEFAULT_SECRET_PROJECT_ENV_NAMES = (
    "GOOGLE_CLOUD_PROJECT",
    "GCP_PROJECT_ID",
)


def _secret_manager_module():
    return importlib.import_module("google.cloud.secretmanager")


@lru_cache(maxsize=1)
def _secret_manager_client():
    return _secret_manager_module().SecretManagerServiceClient()


def _default_secret_project_id() -> str | None:
    for name in _DEFAULT_SECRET_PROJECT_ENV_NAMES:
        value = os.getenv(name)
        if value is None:
            continue
        stripped = value.strip()
        if stripped:
            return stripped
    return None


def _normalize_secret_resource_name(reference: str) -> str:
    normalized = reference.strip()
    if not normalized:
        raise ValueError("Secret Manager reference must not be empty.")

    if normalized.startswith("projects/"):
        if "/versions/" in normalized:
            return normalized
        return f"{normalized}/versions/{_DEFAULT_SECRET_VERSION}"

    project_id = _default_secret_project_id()
    if not project_id:
        raise ValueError(
            "Secret Manager references require GOOGLE_CLOUD_PROJECT or GCP_PROJECT_ID."
        )

    return (
        f"projects/{project_id}/secrets/{normalized}/versions/{_DEFAULT_SECRET_VERSION}"
    )


def _access_secret_reference(reference: str) -> str:
    response = _secret_manager_client().access_secret_version(
        request={"name": _normalize_secret_resource_name(reference)}
    )
    return response.payload.data.decode("utf-8")


@lru_cache(maxsize=128)
def _resolved_secret_reference(reference: str) -> str:
    return _access_secret_reference(reference).strip()


def _resolved_env_binding(raw_value: str) -> str | None:
    stripped = raw_value.strip()
    if not stripped:
        return None
    if stripped.startswith(_SECRET_REF_PREFIX):
        return _resolved_secret_reference(
            stripped.removeprefix(_SECRET_REF_PREFIX).strip()
        )
    return stripped


def env_value(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value is None:
            continue
        resolved = _resolved_env_binding(value)
        if resolved:
            return resolved
    return None
