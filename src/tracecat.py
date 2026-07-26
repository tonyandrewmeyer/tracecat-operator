# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Functions for interacting with the Tracecat workload.

This module is intentionally free of charming concerns so it can be unit-tested
in isolation and reused outside a charm context.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

API_PORT = 8000
UI_PORT = 3000
LITELLM_PORT = 4000
HEALTH_PATH = "/health"


def get_version(container: Any) -> str | None:
    """Get the running version of the workload from the API."""
    try:
        data = _api_get(container, "/health")
    except Exception:
        logger.debug("could not retrieve workload version", exc_info=True)
        return None
    if isinstance(data, dict):
        return data.get("version")
    return None


def health_check(container: Any, host: str = "localhost", port: int = API_PORT) -> bool:
    """Return True if the API health endpoint responds with status ok."""
    try:
        data = _api_get(container, HEALTH_PATH, host=host, port=port)
    except Exception:
        return False
    return isinstance(data, dict) and data.get("status") == "ok"


def _api_get(container: Any, path: str, host: str = "localhost", port: int = API_PORT) -> Any:
    """Perform a GET against the in-pod API and return parsed JSON.

    Uses urllib so no extra dependency is required in the charm runtime. When
    invoked from a unit test with a fake container, callers should monkeypatch
    this function.
    """
    url = f"http://{host}:{port}{path}"
    # When we have a real Pebble container we could use container.exec, but
    # urllib is simpler and works in the charm process which shares the pod
    # network on K8s.
    with urllib.request.urlopen(url, timeout=10) as resp:
        body = resp.read().decode()
    if not body:
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return body


def make_db_uri(*, host: str, port: str | int, dbname: str, user: str, password: str) -> str:
    """Build a psycopg-style Tracecat DB URI from relation fields.

    Tracecat expects ``postgresql+psycopg://user:password@host:port/dbname``.
    """
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{dbname}"
