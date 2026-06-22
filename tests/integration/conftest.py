# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Shared jubilant fixtures for integration tests.

These tests require a bootstrapped Kubernetes Juju controller. Each test module
uses a temporary model that is torn down on completion.
"""

from __future__ import annotations

import pathlib

import jubilant
import pytest

CHARM_PACKED = sorted(pathlib.Path(__file__).parents[2].glob("tracecat-k8s_*.charm"))
TRACECAT_IMAGE = "ghcr.io/tracecathq/tracecat:1.0.0-beta.49"
TRACECAT_UI_IMAGE = "ghcr.io/tracecathq/tracecat-ui:1.0.0-beta.49"


def charm_path() -> pathlib.Path:
    """Return the path to the locally packed .charm file."""
    assert CHARM_PACKED, "no packed charm found; run `charmcraft pack` before integration tests"
    return CHARM_PACKED[0]


@pytest.fixture(scope="module")
def juju() -> jubilant.Juju:
    """Deploy the full Tracecat stack in a temp model and tear down after."""
    with jubilant.temp_model() as j:
        j.deploy("postgresql-k8s", trust=True)
        j.deploy("redis-k8s")
        j.deploy("temporal-k8s", trust=True)
        j.deploy("temporal-admin-k8s", trust=True)
        # temporal-k8s needs its own database.
        j.deploy("postgresql-k8s", "temporal-db", trust=True)
        j.deploy("traefik-k8s", trust=True)
        j.deploy("s3-integrator")

        j.deploy(
            str(charm_path()),
            "tracecat-k8s",
            resources={
                "tracecat-image": TRACECAT_IMAGE,
                "tracecat-ui-image": TRACECAT_UI_IMAGE,
            },
            trust=True,
        )

        j.integrate("tracecat-k8s:postgresql", "postgresql-k8s")
        j.integrate("tracecat-k8s:temporal-host-info", "temporal-k8s")
        j.integrate("tracecat-k8s:redis", "redis-k8s")
        j.integrate("tracecat-k8s:ingress", "traefik-k8s")
        j.integrate("tracecat-k8s:s3-credentials", "s3-integrator")
        j.integrate("temporal-admin-k8s", "temporal-k8s")
        j.integrate("temporal-k8s", "temporal-db")

        # Wait for tracecat to settle into a non-error state. Some dependencies
        # (temporal, s3) may take a while; we tolerate waiting here.
        j.wait(
            lambda status: status.apps["tracecat-k8s"].status == "active",
            error=lambda status: any(app.status == "error" for app in status.apps.values()),
            timeout=30 * 60,
        )
        yield j
