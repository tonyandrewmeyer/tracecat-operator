# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Integration tests: day-2 operations (backup/restore, secret rotation)."""

from __future__ import annotations

import jubilant


def test_backup_restore(juju: jubilant.Juju) -> None:
    """Run backup, then restore from the returned path, and regain active."""
    result = juju.run("tracecat-k8s/0", "backup", params={"destination": "it-backups/"})
    assert result.success, result
    backup_path = result.results.get("backup-path")
    assert backup_path, f"no backup-path in results: {result.results}"

    juju.wait(
        lambda status: status.apps["tracecat-k8s"].status == "active",
        timeout=10 * 60,
    )

    restore = juju.run("tracecat-k8s/0", "restore", params={"source": backup_path})
    assert restore.success, restore
    juju.wait(
        lambda status: status.apps["tracecat-k8s"].status == "active",
        timeout=15 * 60,
    )


def test_rotate_signing_secret(juju: jubilant.Juju) -> None:
    """Rotating the signing secret succeeds and warns about webhook URLs."""
    result = juju.run("tracecat-k8s/0", "rotate-signing-secret")
    assert result.success, result
    warning = result.results.get("warning", "")
    assert "invalid" in warning.lower() or "webhook" in warning.lower()
    juju.wait(
        lambda status: status.apps["tracecat-k8s"].status == "active",
        timeout=5 * 60,
    )
