"""HTTP helpers for outbound API calls."""

from __future__ import annotations

import os

import certifi


def ca_bundle() -> str:
    """Return the CA bundle used for outbound HTTPS requests.

    Prefer an app-level override, then fall back to the standard public
    certificate bundle. This avoids machine-wide SSL_CERT_FILE or
    REQUESTS_CA_BUNDLE settings that may point to a private CA only.
    """
    return os.getenv("FOEHNCAST_CA_BUNDLE") or certifi.where()
