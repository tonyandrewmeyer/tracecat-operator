# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for action error paths and edge branches."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import ops
import pytest
from ops.testing import Harness

import charm


@pytest.fixture
def harness() -> Harness:
    h = Harness(charm.TracecatK8sCharm)
    h.set_can_connect("tracecat", True)
    h.set_can_connect("tracecat-ui", True)
    h.set_leader(True)
    h.begin()
    h.charm._ensure_auto_secrets()
    return h


def _mock_container(h: Harness, *, exec_side_effect=None) -> MagicMock:
    mock = MagicMock()
    mock.can_connect.return_value = True
    if exec_side_effect is not None:
        mock.exec.side_effect = exec_side_effect
    else:
        mock.exec.return_value.wait_output.return_value = (b"ok", b"")
    mock.get_services.return_value = {}
    return mock


def _set_relations(h: Harness) -> None:
    pg = h.add_relation("postgresql", "postgresql-k8s")
    h.add_relation_unit(pg, "postgresql-k8s/0")
    h.update_relation_data(pg, "postgresql-k8s", {"uris": "postgresql://u:p@h:5432/tracecat"})
    rd = h.add_relation("redis", "redis-k8s")
    h.add_relation_unit(rd, "redis-k8s/0")
    h.update_relation_data(rd, "redis-k8s/0", {"hostname": "rh", "port": "6379"})
    tp = h.add_relation("temporal-host-info", "temporal-k8s")
    h.add_relation_unit(tp, "temporal-k8s/0")
    h.update_relation_data(tp, "temporal-k8s", {"host": "th", "port": "7233"})


def _s3_patch(h: Harness):
    return patch.object(
        type(h.charm),
        "_s3_info",
        new_callable=lambda: property(
            lambda self: {
                "endpoint": "http://s3:9000",
                "access-key": "a",
                "secret-key": "b",
                "bucket": "bk",
            }
        ),
    )


class TestActionErrorPaths:
    def test_create_superadmin_exec_failure(self, harness: Harness) -> None:
        harness.charm._set_secret(charm.SECRET_SUPERADMIN_EMAIL, "ops@example.com")
        mock = _mock_container(harness, exec_side_effect=ops.pebble.Error("boom"))
        harness.charm.unit.get_container = lambda name: mock
        event = MagicMock()
        harness.charm._on_create_superadmin(event)
        event.fail.assert_called_once()

    def test_backup_s3_upload_failure_still_succeeds(self, harness: Harness) -> None:
        # pg_dump succeeds (first exec), then mc upload fails (second exec).
        _set_relations(harness)
        mock = MagicMock()
        mock.can_connect.return_value = True
        mock.exec.side_effect = [
            MagicMock(wait_output=MagicMock(return_value=(b"", b""))),
            ops.pebble.Error("mc failed"),
        ]
        harness.charm.unit.get_container = lambda name: mock
        with _s3_patch(harness):
            event = MagicMock()
            event.params = {"destination": "backups/"}
            harness.charm._on_backup(event)
        event.set_results.assert_called_once()

    def test_restore_exec_failure(self, harness: Harness) -> None:
        _set_relations(harness)
        mock = _mock_container(harness, exec_side_effect=ops.pebble.Error("restore boom"))
        harness.charm.unit.get_container = lambda name: mock
        with _s3_patch(harness):
            event = MagicMock()
            event.params = {"source": "backups/tracecat.dump"}
            harness.charm._on_restore(event)
        event.fail.assert_called_once()

    def test_rotate_encryption_key_exec_failure(self, harness: Harness) -> None:
        mock = _mock_container(harness, exec_side_effect=ops.pebble.Error("rotate boom"))
        harness.charm.unit.get_container = lambda name: mock
        event = MagicMock()
        harness.charm._on_rotate_encryption_key(event)
        # Rotation still updates the secret even if the in-place re-encrypt failed.
        event.set_results.assert_called_once()

    def test_export_audit_log_exec_failure(self, harness: Harness) -> None:
        mock = _mock_container(harness, exec_side_effect=ops.pebble.Error("audit boom"))
        harness.charm.unit.get_container = lambda name: mock
        event = MagicMock()
        event.params = {"since": "", "format": "json"}
        harness.charm._on_export_audit_log(event)
        event.fail.assert_called_once()

    def test_backup_no_db(self, harness: Harness) -> None:
        with _s3_patch(harness):
            event = MagicMock()
            event.params = {"destination": "backups/"}
            harness.charm._on_backup(event)
        event.fail.assert_called_once()

    def test_restore_no_s3(self, harness: Harness) -> None:
        mock = _mock_container(harness)
        harness.charm.unit.get_container = lambda name: mock
        event = MagicMock()
        event.params = {"source": "x"}
        harness.charm._on_restore(event)
        event.fail.assert_called_once()


class TestDbUriSecretPath:
    def test_db_uri_no_relation(self, harness: Harness) -> None:
        assert harness.charm._db_uri is None


class TestHandlersAndLayer:
    def test_on_temporal_changed(self, harness: Harness) -> None:
        _set_relations(harness)
        mock = _mock_container(harness)
        harness.charm.unit.get_container = lambda name: mock
        with (
            patch("charm.tracecat.health_check", return_value=True),
            patch("charm.tracecat.get_version", return_value="v"),
            patch("charm.time.sleep"),
        ):
            harness.charm._on_temporal_changed(MagicMock())
        assert isinstance(harness.model.unit.status, ops.ActiveStatus)

    def test_on_ingress_ready(self, harness: Harness) -> None:
        _set_relations(harness)
        mock = _mock_container(harness)
        ui = MagicMock()
        ui.can_connect.return_value = True
        harness.charm.unit.get_container = lambda name: ui if name == "tracecat-ui" else mock
        with patch.object(
            type(harness.charm),
            "_ingress_url",
            new_callable=lambda: property(lambda self: "http://ingress"),
        ):
            with (
                patch("charm.tracecat.health_check", return_value=True),
                patch("charm.tracecat.get_version", return_value="v"),
                patch("charm.time.sleep"),
            ):
                harness.charm._on_ingress_ready(MagicMock())
        ui.add_layer.assert_called()

    def test_on_tracecat_pebble_ready(self, harness: Harness) -> None:
        _set_relations(harness)
        mock = _mock_container(harness)
        harness.charm.unit.get_container = lambda name: mock
        with (
            patch("charm.tracecat.health_check", return_value=True),
            patch("charm.tracecat.get_version", return_value="v"),
            patch("charm.time.sleep"),
        ):
            harness.charm._on_tracecat_pebble_ready(MagicMock())
        assert isinstance(harness.model.unit.status, ops.ActiveStatus)

    def test_config_changed_replans_ui(self, harness: Harness) -> None:
        _set_relations(harness)
        mock = _mock_container(harness)
        ui = MagicMock()
        ui.can_connect.return_value = True
        harness.charm.unit.get_container = lambda name: ui if name == "tracecat-ui" else mock
        with (
            patch("charm.tracecat.health_check", return_value=True),
            patch("charm.tracecat.get_version", return_value="v"),
            patch("charm.time.sleep"),
        ):
            harness.update_config({"log-level": "INFO"})
        ui.replan.assert_called()

    def test_tracing_endpoint_in_env(self, harness: Harness) -> None:
        tracing = MagicMock()
        tracing.otlp_grpc_endpoint.return_value = "http://tempo:4317"
        tracing.otlp_http_endpoint.return_value = None
        harness.charm._tracing = tracing
        env = harness.charm._tracecat_env()
        assert env["OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://tempo:4317"
