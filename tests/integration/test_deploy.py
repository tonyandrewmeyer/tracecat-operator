# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Integration tests: happy-path deploy smoke tests."""

from __future__ import annotations

import json
import urllib.request

import jubilant


def _unit_address(juju: jubilant.Juju, app: str = "tracecat-k8s") -> str:
    status = juju.status()
    units = status.apps[app].units
    unit = next(iter(units.values()))
    return unit.address


def test_api_health(juju: jubilant.Juju) -> None:
    """GET /health returns {"status": "ok"}."""
    addr = _unit_address(juju)
    resp = urllib.request.urlopen(f"http://{addr}:8000/health", timeout=30)
    data = json.loads(resp.read().decode())
    assert data.get("status") == "ok"


def test_ui_reachable(juju: jubilant.Juju) -> None:
    """The tracecat-ui container responds on port 3000."""
    addr = _unit_address(juju)
    resp = urllib.request.urlopen(f"http://{addr}:3000", timeout=30)
    assert resp.status == 200


def test_status_active(juju: jubilant.Juju) -> None:
    """tracecat-k8s reports active/idle."""
    status = juju.status()
    assert status.apps["tracecat-k8s"].status == "active"


def test_temporal_round_trip(juju: jubilant.Juju) -> None:
    """Worker and executor Pebble services are running after temporal relation."""
    out = juju.cli("ssh", "--container", "tracecat", "tracecat-k8s/0", "pebble", "services")
    assert "api" in out
    assert "worker" in out
    assert "executor" in out
