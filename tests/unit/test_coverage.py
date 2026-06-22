# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Additional unit tests covering action handlers and event wiring."""

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


def _mock_container(h: Harness) -> MagicMock:
    mock = MagicMock()
    mock.can_connect.return_value = True
    mock.exec.return_value.wait_output.return_value = (b"ok", b"")
    mock.get_services.return_value = {}
    ui = MagicMock()
    ui.can_connect.return_value = True
    h.charm.unit.get_container = lambda name: mock if name == "tracecat" else ui
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


class TestActionsExtended:
    def test_create_superadmin_success(self, harness: Harness) -> None:
        harness.charm._set_secret(charm.SECRET_SUPERADMIN_EMAIL, "ops@example.com")
        _mock_container(harness)
        event = MagicMock()
        harness.charm._on_create_superadmin(event)
        event.set_results.assert_called_once()

    def test_create_superadmin_container_not_ready(self, harness: Harness) -> None:
        harness.charm._set_secret(charm.SECRET_SUPERADMIN_EMAIL, "ops@example.com")
        mock = MagicMock()
        mock.can_connect.return_value = False
        harness.charm.unit.get_container = lambda name: mock
        event = MagicMock()
        harness.charm._on_create_superadmin(event)
        event.fail.assert_called_once()

    def test_backup_success(self, harness: Harness) -> None:
        _set_relations(harness)
        _mock_container(harness)
        with patch.object(
            type(harness.charm),
            "_s3_info",
            new_callable=lambda: property(
                lambda self: {
                    "endpoint": "http://s3:9000",
                    "access-key": "a",
                    "secret-key": "b",
                    "bucket": "bk",
                }
            ),
        ):
            event = MagicMock()
            event.params = {"destination": "backups/"}
            harness.charm._on_backup(event)
        event.set_results.assert_called_once()
        assert event.set_results.call_args[0][0]["status"] == "ok"

    def test_backup_pg_dump_fails(self, harness: Harness) -> None:
        _set_relations(harness)
        mock = _mock_container(harness)
        # First exec is migrations-free here (backup calls pg_dump directly);
        # make pg_dump fail.
        mock.exec.side_effect = ops.pebble.Error("dump failed")
        with patch.object(
            type(harness.charm),
            "_s3_info",
            new_callable=lambda: property(
                lambda self: {
                    "endpoint": "e",
                    "access-key": "a",
                    "secret-key": "b",
                    "bucket": "bk",
                }
            ),
        ):
            event = MagicMock()
            event.params = {"destination": "backups/"}
            harness.charm._on_backup(event)
        event.fail.assert_called_once()

    def test_restore_success(self, harness: Harness) -> None:
        _set_relations(harness)
        _mock_container(harness)
        with patch.object(
            type(harness.charm),
            "_s3_info",
            new_callable=lambda: property(
                lambda self: {
                    "endpoint": "e",
                    "access-key": "a",
                    "secret-key": "b",
                    "bucket": "bk",
                }
            ),
        ):
            event = MagicMock()
            event.params = {"source": "backups/tracecat.dump"}
            with patch("charm.tracecat.health_check", return_value=True):
                harness.charm._on_restore(event)
        event.set_results.assert_called_once()

    def test_restore_without_source_fails(self, harness: Harness) -> None:
        _mock_container(harness)
        event = MagicMock()
        event.params = {"source": ""}
        harness.charm._on_restore(event)
        event.fail.assert_called_once()

    def test_rotate_encryption_key(self, harness: Harness) -> None:
        _mock_container(harness)
        old = harness.charm._secret_value(charm.SECRET_DB_ENCRYPTION_KEY)
        event = MagicMock()
        harness.charm._on_rotate_encryption_key(event)
        event.set_results.assert_called_once()
        new = harness.charm._get_secret(charm.SECRET_DB_ENCRYPTION_KEY).get_content(refresh=True)[
            "value"
        ]
        assert new != old

    def test_upgrade_schema_success(self, harness: Harness) -> None:
        _mock_container(harness)
        event = MagicMock()
        harness.charm._on_upgrade_schema(event)
        event.set_results.assert_called_once()

    def test_upgrade_schema_failure(self, harness: Harness) -> None:
        mock = _mock_container(harness)
        mock.exec.side_effect = ops.pebble.Error("alembic fail")
        event = MagicMock()
        harness.charm._on_upgrade_schema(event)
        event.fail.assert_called_once()

    def test_scale_workers_out_of_range(self, harness: Harness) -> None:
        _mock_container(harness)
        event = MagicMock()
        event.params = {"pool-size": 100}
        harness.charm._on_scale_workers(event)
        event.fail.assert_called_once()

    def test_scale_workers_no_container(self, harness: Harness) -> None:
        mock = MagicMock()
        mock.can_connect.return_value = False
        harness.charm.unit.get_container = lambda name: mock
        event = MagicMock()
        event.params = {"pool-size": 3}
        harness.charm._on_scale_workers(event)
        event.fail.assert_called_once()

    def test_export_audit_log_csv(self, harness: Harness) -> None:
        mock = _mock_container(harness)
        mock.exec.return_value.wait_output.return_value = (b'[{"id": 1, "user": "x"}]', b"")
        event = MagicMock()
        event.params = {"since": "", "format": "csv"}
        harness.charm._on_export_audit_log(event)
        event.set_results.assert_called_once()
        assert "id,user" in event.set_results.call_args[0][0]["log"]

    def test_export_audit_log_no_container(self, harness: Harness) -> None:
        mock = MagicMock()
        mock.can_connect.return_value = False
        harness.charm.unit.get_container = lambda name: mock
        event = MagicMock()
        event.params = {"since": "", "format": "json"}
        harness.charm._on_export_audit_log(event)
        event.fail.assert_called_once()


class TestEventHandlers:
    def test_install_triggers_reconcile(self, harness: Harness) -> None:
        _mock_container(harness)
        # install with no relations → waiting (not error).
        harness.charm._on_install(MagicMock())
        assert isinstance(
            harness.model.unit.status, (ops.WaitingStatus, ops.BlockedStatus, ops.ActiveStatus)
        )

    def test_config_changed_validates_and_reconciles(self, harness: Harness) -> None:
        _set_relations(harness)
        _mock_container(harness)
        with (
            patch("charm.tracecat.health_check", return_value=True),
            patch("charm.tracecat.get_version", return_value="1.0.0"),
        ):
            harness.update_config({"log-level": "DEBUG"})
        assert harness.charm.config["log-level"] == "DEBUG"

    def test_config_changed_invalid_blocks(self, harness: Harness) -> None:
        harness.update_config({"log-level": "nonsense"})
        assert isinstance(harness.model.unit.status, ops.BlockedStatus)

    def test_upgrade_charm_regenerates_secrets(self, harness: Harness) -> None:
        _mock_container(harness)
        harness.charm._on_upgrade_charm(MagicMock())
        # secrets still present after upgrade.
        assert harness.charm._secret_value(charm.SECRET_SERVICE_KEY) != ""

    def test_ui_pebble_ready(self, harness: Harness) -> None:
        ui = MagicMock()
        ui.can_connect.return_value = True
        tracecat = MagicMock()
        tracecat.can_connect.return_value = True
        harness.charm.unit.get_container = lambda name: ui if name == "tracecat-ui" else tracecat
        harness.charm._on_ui_pebble_ready(MagicMock())
        ui.add_layer.assert_called_once()
        ui.replan.assert_called_once()

    def test_ui_pebble_ready_not_connected(self, harness: Harness) -> None:
        ui = MagicMock()
        ui.can_connect.return_value = False
        harness.charm.unit.get_container = lambda name: ui
        harness.charm._on_ui_pebble_ready(MagicMock())
        ui.add_layer.assert_not_called()

    def test_reconcile_full_path(self, harness: Harness) -> None:
        _set_relations(harness)
        _mock_container(harness)
        with (
            patch("charm.tracecat.health_check", return_value=True),
            patch("charm.tracecat.get_version", return_value="v1"),
        ):
            harness.charm._reconcile(None)
        assert isinstance(harness.model.unit.status, ops.ActiveStatus)

    def test_reconcile_blocked_on_bad_config(self, harness: Harness) -> None:
        harness.update_config({"log-level": "bad"})
        harness.charm._reconcile(None)
        assert isinstance(harness.model.unit.status, ops.BlockedStatus)

    def test_start_core_services_container_not_ready(self, harness: Harness) -> None:
        _set_relations(harness)
        mock = MagicMock()
        mock.can_connect.return_value = False
        harness.charm.unit.get_container = lambda name: mock
        harness.charm._start_core_services()
        assert isinstance(harness.model.unit.status, ops.WaitingStatus)

    def test_api_health_failure_blocks(self, harness: Harness) -> None:
        _set_relations(harness)
        _mock_container(harness)
        with patch("charm.tracecat.health_check", return_value=False), patch("charm.time.sleep"):
            harness.charm._start_core_services()
        assert isinstance(harness.model.unit.status, ops.BlockedStatus)

    def test_temporal_override_used(self, harness: Harness) -> None:
        harness.update_config({"temporal-host-override": "override:7233"})
        _set_relations(harness)
        _mock_container(harness)
        with (
            patch("charm.tracecat.health_check", return_value=True),
            patch("charm.tracecat.get_version", return_value="v"),
        ):
            harness.charm._reconcile(None)
        # temporal override takes precedence.
        assert harness.charm._temporal_url == "override:7233"


class TestEnvExtras:
    def test_env_oidc(self, harness: Harness) -> None:
        harness.charm._set_secret(charm.SECRET_OIDC_CLIENT_SECRET, "secret")
        harness.update_config(
            {
                "auth-types": "basic,oidc",
                "oidc-issuer": "https://idp.example.com",
                "oidc-client-id": "tracecat",
            }
        )
        env = harness.charm._tracecat_env()
        assert env["OIDC_ISSUER"] == "https://idp.example.com"
        assert env["OIDC_CLIENT_ID"] == "tracecat"
        assert env["OIDC_CLIENT_SECRET"] == "secret"

    def test_env_sentry_dsn(self, harness: Harness) -> None:
        harness.update_config({"sentry-dsn": "https://sentry/1"})
        env = harness.charm._tracecat_env()
        assert env["SENTRY_DSN"] == "https://sentry/1"

    def test_env_agent_features_disabled_by_default(self, harness: Harness) -> None:
        layer = harness.charm._tracecat_layer()
        assert "litellm" not in layer.services
        assert "mcp" not in layer.services

    def test_env_ingress_url(self, harness: Harness) -> None:
        with patch.object(
            type(harness.charm),
            "_ingress_url",
            new_callable=lambda: property(lambda self: "http://ingress.example.com"),
        ):
            env = harness.charm._tracecat_env()
        assert env["TRACECAT__PUBLIC_API_URL"] == "http://ingress.example.com/api"
