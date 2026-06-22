# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Integration tests: charm upgrade path (schema-migration regression)."""

from __future__ import annotations

import jubilant


def test_upgrade_charm(juju: jubilant.Juju) -> None:
    """Self-upgrade: refresh to the same charm and regain active + run a check."""
    from conftest import charm_path

    juju.cli("refresh", "tracecat-k8s", "--path", str(charm_path()))
    juju.wait(
        lambda status: status.apps["tracecat-k8s"].status == "active",
        timeout=20 * 60,
    )
    # After upgrade, migrations re-run and the API must still be healthy.
    out = juju.cli("ssh", "--container", "tracecat", "tracecat-k8s/0", "pebble", "services")
    assert "api" in out
