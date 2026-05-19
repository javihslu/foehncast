"""Tests for environment binding helpers."""

from __future__ import annotations

import foehncast.env as env


def test_normalize_secret_resource_name_uses_default_project(monkeypatch) -> None:
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.setenv("GCP_PROJECT_ID", "demo-project")

    assert env._normalize_secret_resource_name("composer-api-token") == (
        "projects/demo-project/secrets/composer-api-token/versions/latest"
    )


def test_normalize_secret_resource_name_accepts_resource_paths() -> None:
    assert (
        env._normalize_secret_resource_name(
            "projects/demo-project/secrets/composer-api-token"
        )
        == "projects/demo-project/secrets/composer-api-token/versions/latest"
    )
    assert (
        env._normalize_secret_resource_name(
            "projects/demo-project/secrets/composer-api-token/versions/5"
        )
        == "projects/demo-project/secrets/composer-api-token/versions/5"
    )


def test_env_value_resolves_secret_references(monkeypatch) -> None:
    monkeypatch.setenv("PRIMARY_SECRET", "sm://composer-api-token")
    monkeypatch.setattr(env, "_access_secret_reference", lambda reference: " resolved ")
    env._resolved_secret_reference.cache_clear()

    try:
        assert env.env_value("PRIMARY_SECRET") == "resolved"
    finally:
        env._resolved_secret_reference.cache_clear()
