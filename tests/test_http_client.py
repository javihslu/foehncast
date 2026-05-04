"""Tests for outbound HTTP helper configuration."""

from __future__ import annotations

import certifi
import pytest

from foehncast import http_client


def test_ca_bundle_prefers_app_specific_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FOEHNCAST_CA_BUNDLE", "/tmp/foehncast-ca.pem")
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", "/tmp/requests-ca.pem")
    monkeypatch.setenv("SSL_CERT_FILE", "/tmp/private-root.pem")

    assert http_client.ca_bundle() == "/tmp/foehncast-ca.pem"


def test_ca_bundle_ignores_requests_ca_bundle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FOEHNCAST_CA_BUNDLE", raising=False)
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", "/tmp/requests-ca.pem")
    monkeypatch.setenv("SSL_CERT_FILE", "/tmp/private-root.pem")

    assert http_client.ca_bundle() == certifi.where()


def test_ca_bundle_ignores_machine_ssl_cert_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FOEHNCAST_CA_BUNDLE", raising=False)
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)
    monkeypatch.setenv("SSL_CERT_FILE", "/tmp/private-root.pem")

    assert http_client.ca_bundle() == certifi.where()
