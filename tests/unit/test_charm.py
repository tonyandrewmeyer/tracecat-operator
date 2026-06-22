# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the tracecat-k8s charm."""

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
    return h


def _patch_container(charm_obj: charm.TracecatK8sCharm) -> MagicMock:
    """Replace the tracecat container with a mock that records calls."""
    mock = MagicMock()
    mock.can_connect.return_value = True
    mock.exec.return_value.wait_output.return_value = (b"ok", b"")
    mock.get_services.return_value = {}
    ui_mock = MagicMock()
    ui_mock.can_connect.return_value = True
    charm_obj.unit.get_container = lambda name: mock if name == "tracecat" else ui_mock
    return mock


class TestSecrets:
    def test_install_generates_auto_secrets(self, harness: Harness) -> None:
        harness.charm._ensure_auto_secrets()
        for label in (
            charm.SECRET_DB_ENCRYPTION_KEY,
            charm.SECRET_SERVICE_KEY,
            charm.SECRET_SIGNING_SECRET,
            charm.SECRET_USER_AUTH_SECRET,
        ):
            secret = harness.charm.model.get_secret(label=label)
            assert secret is not None, f"secret {label} not created"
            content = secret.get_content()
            assert content.get("value"), f"secret {label} has empty value"

    def test_secrets_not_regenerated_on_rerun(self, harness: Harness) -> None:
        harness.charm._ensure_auto_secrets()
        first = harness.charm._secret_value(charm.SECRET_SERVICE_KEY)
        harness.charm._ensure_auto_secrets()
        second = harness.charm._secret_value(charm.SECRET_SERVICE_KEY)
        assert first == second

    def test_db_encryption_key_is_valid_fernet(self, harness: Harness) -> None:
        from cryptography.fernet import Fernet

        harness.charm._ensure_auto_secrets()
        key = harness.charm._secret_value(charm.SECRET_DB_ENCRYPTION_KEY)
        assert key != ""
        # Must be a usable Fernet key.
        f = Fernet(key.encode())
        token = f.encrypt(b"test")
        assert f.decrypt(token) == b"test"


class TestConfigValidation:
    def test_invalid_log_level_blocks(self, harness: Harness) -> None:
        harness.update_config({"log-level": "trace"})
        assert harness.charm._validate_config() is False
        assert isinstance(harness.model.unit.status, ops.BlockedStatus)

    def test_valid_log_level_passes(self, harness: Harness) -> None:
        for level in ("DEBUG", "INFO", "WARNING", "ERROR"):
            harness.update_config({"log-level": level})
            assert harness.charm._validate_config() is True

    def test_oidc_without_issuer_blocks(self, harness: Harness) -> None:
        harness.update_config({"auth-types": "basic,oidc"})
        assert harness.charm._validate_config() is False
        assert "oidc" in str(harness.model.unit.status).lower()

    def test_oidc_with_issuer_passes(self, harness: Harness) -> None:
        harness.update_config(
            {
                "auth-types": "basic,oidc",
                "oidc-issuer": "https://idp.example.com",
                "oidc-client-id": "tracecat",
            }
        )
        assert harness.charm._validate_config() is True


class TestEnv:
    def test_env_has_required_keys(self, harness: Harness) -> None:
        harness.charm._ensure_auto_secrets()
        with (
            patch.object(
                type(harness.charm),
                "_db_uri",
                new_callable=lambda: property(
                    lambda self: "postgresql+psycopg://u:p@h:5432/tracecat"
                ),
            ),
            patch.object(
                type(harness.charm),
                "_redis_url",
                new_callable=lambda: property(lambda self: "redis://r:6379"),
            ),
            patch.object(
                type(harness.charm),
                "_temporal_url",
                new_callable=lambda: property(lambda self: "t:7233"),
            ),
        ):
            env = harness.charm._tracecat_env()
        assert env["TRACECAT__APP_ENV"] == "production"
        assert env["TRACECAT__DB_URI"] == "postgresql+psycopg://u:p@h:5432/tracecat"
        assert env["REDIS_URL"] == "redis://r:6379"
        assert env["TEMPORAL__CLUSTER_URL"] == "t:7233"
        assert env["TRACECAT__DB_ENCRYPTION_KEY"] != ""
        assert env["TRACECAT__SERVICE_KEY"] != ""
        assert env["TRACECAT__SIGNING_SECRET"] != ""

    def test_db_uri_scheme_conversion(self, harness: Harness) -> None:
        rel_id = harness.add_relation("postgresql", "postgresql-k8s")
        harness.add_relation_unit(rel_id, "postgresql-k8s/0")
        harness.update_relation_data(
            rel_id, "postgresql-k8s", {"uris": "postgresql://u:p@h:5432/tracecat"}
        )
        assert harness.charm._db_uri == "postgresql+psycopg://u:p@h:5432/tracecat"

    def test_temporal_host_override(self, harness: Harness) -> None:
        harness.update_config({"temporal-host-override": "manual.host:7233"})
        assert harness.charm._temporal_url == "manual.host:7233"


class TestStartupSequence:
    def test_relations_not_ready_waits(self, harness: Harness) -> None:
        # No relations set → waiting.
        assert harness.charm._relations_ready is False
        assert isinstance(harness.model.unit.status, ops.WaitingStatus)

    def test_postgres_only_still_waits_for_redis(self, harness: Harness) -> None:
        rel_id = harness.add_relation("postgresql", "postgresql-k8s")
        harness.add_relation_unit(rel_id, "postgresql-k8s/0")
        harness.update_relation_data(
            rel_id, "postgresql-k8s", {"uris": "postgresql://u:p@h:5432/tracecat"}
        )
        assert harness.charm._relations_ready is False
        assert "redis" in str(harness.model.unit.status)

    def test_all_relations_active(self, harness: Harness) -> None:
        harness.charm._ensure_auto_secrets()
        pg = harness.add_relation("postgresql", "postgresql-k8s")
        harness.add_relation_unit(pg, "postgresql-k8s/0")
        harness.update_relation_data(
            pg, "postgresql-k8s", {"uris": "postgresql://u:p@h:5432/tracecat"}
        )
        rd = harness.add_relation("redis", "redis-k8s")
        harness.add_relation_unit(rd, "redis-k8s/0")
        harness.update_relation_data(rd, "redis-k8s/0", {"hostname": "redis-host", "port": "6379"})
        tp = harness.add_relation("temporal-host-info", "temporal-k8s")
        harness.add_relation_unit(tp, "temporal-k8s/0")
        harness.update_relation_data(tp, "temporal-k8s", {"host": "temporal-host", "port": "7233"})
        mock = _patch_container(harness.charm)
        with (
            patch("charm.tracecat.health_check", return_value=True),
            patch("charm.tracecat.get_version", return_value="1.0.0-beta.49"),
        ):
            harness.charm._start_core_services()

        # migrations + api + worker + executor started.
        started = [c.args[0] for c in mock.start.call_args_list]
        assert "api" in started
        assert "worker" in started
        assert "executor" in started
        assert isinstance(harness.model.unit.status, ops.ActiveStatus)

    def test_migration_failure_blocks(self, harness: Harness) -> None:
        harness.charm._ensure_auto_secrets()
        with (
            patch.object(
                type(harness.charm),
                "_db_uri",
                new_callable=lambda: property(
                    lambda self: "postgresql+psycopg://u:p@h:5432/tracecat"
                ),
            ),
            patch.object(
                type(harness.charm),
                "_redis_url",
                new_callable=lambda: property(lambda self: "redis://r:6379"),
            ),
            patch.object(
                type(harness.charm),
                "_temporal_url",
                new_callable=lambda: property(lambda self: "t:7233"),
            ),
        ):
            mock = _patch_container(harness.charm)
            mock.exec.side_effect = ops.pebble.Error("migrations failed")
            harness.charm._start_core_services()
        assert isinstance(harness.model.unit.status, ops.BlockedStatus)


class TestActions:
    def test_scale_workers_validation(self, harness: Harness) -> None:
        _patch_container(harness.charm)
        event = MagicMock()
        event.params = {"pool-size": 0}
        harness.charm._on_scale_workers(event)
        event.fail.assert_called_once()
        assert "1 and 50" in event.fail.call_args[0][0]

    def test_scale_workers_success(self, harness: Harness) -> None:
        harness.charm._ensure_auto_secrets()
        mock = _patch_container(harness.charm)
        event = MagicMock()
        event.params = {"pool-size": 10}
        with (
            patch.object(
                type(harness.charm), "_db_uri", new_callable=lambda: property(lambda self: None)
            ),
        ):
            harness.charm._on_scale_workers(event)
        event.set_results.assert_called_once()
        mock.restart.assert_called_once_with("executor")

    def test_rotate_signing_secret_updates_secret(self, harness: Harness) -> None:
        harness.charm._ensure_auto_secrets()
        old = harness.charm._secret_value(charm.SECRET_SIGNING_SECRET)
        _patch_container(harness.charm)
        event = MagicMock()
        harness.charm._on_rotate_signing_secret(event)
        new = harness.charm._get_secret(charm.SECRET_SIGNING_SECRET).get_content(refresh=True)[
            "value"
        ]
        assert new != old
        assert "invalid" in event.set_results.call_args[0][0]["warning"].lower()

    def test_rotate_service_key_updates_secret(self, harness: Harness) -> None:
        harness.charm._ensure_auto_secrets()
        old = harness.charm._secret_value(charm.SECRET_SERVICE_KEY)
        _patch_container(harness.charm)
        event = MagicMock()
        harness.charm._on_rotate_service_key(event)
        assert (
            harness.charm._get_secret(charm.SECRET_SERVICE_KEY).get_content(refresh=True)["value"]
            != old
        )

    def test_backup_without_s3_fails(self, harness: Harness) -> None:
        event = MagicMock()
        harness.charm._on_backup(event)
        event.fail.assert_called_once()

    def test_create_superadmin_without_email_fails(self, harness: Harness) -> None:
        _patch_container(harness.charm)
        event = MagicMock()
        harness.charm._on_create_superadmin(event)
        event.fail.assert_called_once()
        assert "superadmin-email" in event.fail.call_args[0][0]

    def test_export_audit_log_returns_content(self, harness: Harness) -> None:
        harness.charm._ensure_auto_secrets()
        mock = _patch_container(harness.charm)
        mock.exec.return_value.wait_output.return_value = (b'[{"id": 1}]', b"")
        event = MagicMock()
        event.params = {"since": "2026-01-01T00:00:00Z", "format": "json"}
        harness.charm._on_export_audit_log(event)
        event.set_results.assert_called_once()
        assert "log" in event.set_results.call_args[0][0]


class TestLayer:
    def test_agent_services_gated(self, harness: Harness) -> None:
        layer = harness.charm._tracecat_layer()
        services = layer.services
        assert "api" in services
        assert "worker" in services
        assert "executor" in services
        assert "agent-worker" not in services
        assert "litellm" not in services

        harness.update_config({"enable-agent-features": True})
        layer = harness.charm._tracecat_layer()
        assert "agent-worker" in layer.services
        assert "litellm" in layer.services

    def test_ui_layer_command(self, harness: Harness) -> None:
        layer = harness.charm._ui_layer()
        assert layer.services["ui"].command == "node server.js"
        assert layer.services["ui"].environment["PORT"] == "3000"

    def test_migrations_run_via_exec(self, harness: Harness) -> None:
        harness.charm._ensure_auto_secrets()
        with (
            patch.object(
                type(harness.charm),
                "_db_uri",
                new_callable=lambda: property(
                    lambda self: "postgresql+psycopg://u:p@h:5432/tracecat"
                ),
            ),
            patch.object(
                type(harness.charm),
                "_redis_url",
                new_callable=lambda: property(lambda self: "redis://r:6379"),
            ),
            patch.object(
                type(harness.charm),
                "_temporal_url",
                new_callable=lambda: property(lambda self: "t:7233"),
            ),
        ):
            mock = _patch_container(harness.charm)
            with patch("charm.tracecat.health_check", return_value=True):
                harness.charm._start_core_services()
        # First exec call is the alembic migration.
        first_cmd = mock.exec.call_args_list[0].args[0]
        assert "alembic" in first_cmd
        assert "upgrade" in first_cmd
