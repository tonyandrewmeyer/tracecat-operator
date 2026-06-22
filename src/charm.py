#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charm the Tracecat application.

The charm deploys Tracecat (an open-source SOAR platform) on Kubernetes using
two OCI containers:

* ``tracecat`` — the FastAPI server, Temporal workers, and the activity
  executor (plus optional AI-agent services), all from
  ``ghcr.io/tracecathq/tracecat``.
* ``tracecat-ui`` — the Next.js frontend from
  ``ghcr.io/tracecathq/tracecat-ui``.

All persistent state lives in relations (PostgreSQL, Redis, Temporal, S3); the
charm itself is stateless and every credential is a Juju secret.
"""

from __future__ import annotations

import json
import logging
import secrets as pysecrets
import time
from typing import Any

import ops
from charms.data_platform_libs.v0.data_interfaces import DatabaseRequires
from charms.data_platform_libs.v0.s3 import S3Requirer
from charms.grafana_k8s.v0.grafana_dashboard import GrafanaDashboardProvider
from charms.loki_k8s.v1.loki_push_api import LogForwarder
from charms.prometheus_k8s.v0.prometheus_scrape import MetricsEndpointProvider
from charms.redis_k8s.v0.redis import RedisRelationCharmEvents, RedisRequires
from charms.tempo_coordinator_k8s.v0.tracing import TracingEndpointRequirer
from charms.temporal_k8s.v0.temporal_host_info import TemporalHostInfoRequirer
from charms.tls_certificates_interface.v3.tls_certificates import (
    TLSCertificatesRequiresV3,
)
from charms.traefik_k8s.v2.ingress import IngressPerAppRequirer
from cryptography.fernet import Fernet

import tracecat

logger = logging.getLogger(__name__)

# Container names (must match charmcraft.yaml `containers:`).
TRACECAT_CONTAINER = "tracecat"
UI_CONTAINER = "tracecat-ui"

# Pebble service names.
SVC_API = "api"
SVC_WORKER = "worker"
SVC_EXECUTOR = "executor"
SVC_AGENT_WORKER = "agent-worker"
SVC_AGENT_EXECUTOR = "agent-executor"
SVC_LITELLM = "litellm"
SVC_MCP = "mcp"
SVC_UI = "ui"

API_PORT = 8000
UI_PORT = 3000
LITELLM_PORT = 4000

# Juju secret labels.
SECRET_DB_ENCRYPTION_KEY = "tracecat-db-encryption-key"
SECRET_SERVICE_KEY = "tracecat-service-key"
SECRET_SIGNING_SECRET = "tracecat-signing-secret"
SECRET_USER_AUTH_SECRET = "tracecat-user-auth-secret"
SECRET_SUPERADMIN_EMAIL = "tracecat-superadmin-email"
SECRET_OIDC_CLIENT_SECRET = "tracecat-oidc-client-secret"

VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR"}


class TracecatCharmEvents(RedisRelationCharmEvents):
    """Charm events, including the redis lib's custom event."""


class TracecatK8sCharm(ops.CharmBase):
    """Charm the Tracecat application."""

    on = TracecatCharmEvents()  # type: ignore[assignment]

    def __init__(self, framework: ops.Framework) -> None:
        super().__init__(framework)
        self._postgresql = DatabaseRequires(self, "postgresql", "tracecat")
        self._redis = RedisRequires(self, "redis")
        self._temporal = TemporalHostInfoRequirer(self)
        self._ingress = IngressPerAppRequirer(self, port=API_PORT)
        self._s3 = S3Requirer(self, "s3-credentials")
        self._certs = TLSCertificatesRequiresV3(self, "certificates")

        # COS-Lite providers.
        self._log_forwarder = LogForwarder(self, relation_name="logging")
        self._metrics = MetricsEndpointProvider(
            self,
            jobs=[{"static_configs": [{"targets": [f"*:{API_PORT}"]}]}],
        )
        self._grafana = GrafanaDashboardProvider(self)
        self._tracing = TracingEndpointRequirer(self, protocols=["otlp_grpc", "otlp_http"])

        framework.observe(self.on.install, self._on_install)
        framework.observe(self.on.config_changed, self._on_config_changed)
        framework.observe(self.on.upgrade_charm, self._on_upgrade_charm)
        framework.observe(self.on[TRACECAT_CONTAINER].pebble_ready, self._on_tracecat_pebble_ready)
        framework.observe(self.on[UI_CONTAINER].pebble_ready, self._on_ui_pebble_ready)
        framework.observe(self._postgresql.on.database_created, self._reconcile)
        framework.observe(self._postgresql.on.endpoints_changed, self._reconcile)
        framework.observe(self.on.redis_relation_updated, self._reconcile)
        framework.observe(self._temporal.on.temporal_host_info_changed, self._on_temporal_changed)
        framework.observe(self._temporal.on.temporal_host_info_unavailable, self._reconcile)
        framework.observe(self._ingress.on.ready, self._on_ingress_ready)
        framework.observe(self._ingress.on.revoked, self._reconcile)
        framework.observe(self._s3.on.credentials_changed, self._reconcile)
        framework.observe(self._certs.on.certificate_available, self._reconcile)
        framework.observe(self.on.secret_changed, self._reconcile)

        # Actions.
        framework.observe(self.on.create_superadmin_action, self._on_create_superadmin)
        framework.observe(self.on.backup_action, self._on_backup)
        framework.observe(self.on.restore_action, self._on_restore)
        framework.observe(self.on.rotate_encryption_key_action, self._on_rotate_encryption_key)
        framework.observe(self.on.rotate_service_key_action, self._on_rotate_service_key)
        framework.observe(self.on.rotate_signing_secret_action, self._on_rotate_signing_secret)
        framework.observe(self.on.upgrade_schema_action, self._on_upgrade_schema)
        framework.observe(self.on.scale_workers_action, self._on_scale_workers)
        framework.observe(self.on.export_audit_log_action, self._on_export_audit_log)

    # ------------------------------------------------------------------ #
    # Properties
    # ------------------------------------------------------------------ #

    @property
    def container(self) -> ops.Container:
        """The tracecat workload container."""
        return self.unit.get_container(TRACECAT_CONTAINER)

    @property
    def ui_container(self) -> ops.Container:
        """The tracecat-ui workload container."""
        return self.unit.get_container(UI_CONTAINER)

    @property
    def _db_uri(self) -> str | None:
        """Return the Tracecat DB URI from the postgresql relation.

        postgresql-k8s publishes ``uris`` either directly in the application
        databag or, when Juju secrets are in use, inside the secret referenced
        by the ``secret-user`` field. Tracecat uses the psycopg3 driver via
        SQLAlchemy, so the ``postgresql://`` scheme is rewritten to
        ``postgresql+psycopg://``.
        """
        relation = self.model.get_relation("postgresql")
        if not relation or not relation.app:
            return None
        app_data = relation.data[relation.app]
        uris = app_data.get("uris")
        if not uris:
            secret_uri = app_data.get("secret-user")
            if secret_uri:
                try:
                    secret = self.model.get_secret(id=secret_uri)
                    uris = secret.get_content().get("uris")
                except ops.SecretNotFoundError:
                    uris = None
        if not uris:
            return None
        uri = uris.split(",")[0].strip()
        if uri.startswith("postgresql://"):
            uri = "postgresql+psycopg://" + uri[len("postgresql://") :]
        return uri

    @property
    def _redis_url(self) -> str | None:
        return self._redis.url

    @property
    def _temporal_url(self) -> str | None:
        override = self.config.get("temporal-host-override", "")
        if override:
            return override
        host = self._temporal.host
        port = self._temporal.port
        if host and port:
            return f"{host}:{port}"
        return None

    @property
    def _s3_info(self) -> dict[str, str]:
        return self._s3.get_s3_connection_info()

    @property
    def _ingress_url(self) -> str | None:
        try:
            return self._ingress.url
        except Exception:  # noqa: BLE001
            return None

    def _get_secret(self, label: str) -> ops.Secret | None:
        """Return the Juju secret for ``label`` or None if it does not exist."""
        try:
            return self.model.get_secret(label=label)
        except ops.SecretNotFoundError:
            return None

    @property
    def _relations_ready(self) -> bool:
        """True when the mandatory day-one relations are satisfied."""
        missing: list[str] = []
        if not self._db_uri:
            missing.append("postgresql")
        if not self._redis_url:
            missing.append("redis")
        # temporal is not mandatory for the API to start; worker/executor
        # remain idle until the temporal relation (or override) is present.
        if missing:
            self.unit.status = ops.WaitingStatus(f"waiting for relations: {', '.join(missing)}")
            return False
        return True

    # ------------------------------------------------------------------ #
    # Secret management
    # ------------------------------------------------------------------ #

    def _ensure_secret(self, label: str, value: str) -> str:
        """Return the secret content for ``label``, creating it if absent."""
        existing = self._get_secret(label)
        if existing is not None:
            return existing.get_content().get("value", "")
        self.app.add_secret({"value": value}, label=label)
        return value

    def _ensure_auto_secrets(self) -> None:
        """Generate the auto-generated secrets on first install."""
        self._ensure_secret(SECRET_DB_ENCRYPTION_KEY, Fernet.generate_key().decode())
        self._ensure_secret(SECRET_SERVICE_KEY, pysecrets.token_hex(32))
        self._ensure_secret(SECRET_SIGNING_SECRET, pysecrets.token_hex(32))
        self._ensure_secret(SECRET_USER_AUTH_SECRET, pysecrets.token_hex(32))

    def _secret_value(self, label: str) -> str:
        secret = self._get_secret(label)
        if secret is None:
            return ""
        return secret.get_content().get("value", "")

    def _set_secret(self, label: str, value: str) -> None:
        """Update an existing secret's value (for rotation)."""
        secret = self._get_secret(label)
        if secret is None:
            self.app.add_secret({"value": value}, label=label)
            return
        secret.set_content({"value": value})

    # ------------------------------------------------------------------ #
    # Environment
    # ------------------------------------------------------------------ #

    def _tracecat_env(self) -> dict[str, str]:
        """Build the environment for the tracecat Pebble services."""
        cfg = self.config
        env: dict[str, str] = {
            "LOG_LEVEL": str(cfg.get("log-level", "INFO")),
            "TRACECAT__APP_ENV": "production",
            "TRACECAT__API_URL": f"http://localhost:{API_PORT}",
            "TRACECAT__API_ROOT_PATH": "/api",
            "TRACECAT__AUTH_TYPES": str(cfg.get("auth-types", "basic")),
            "TRACECAT__AUTH_ALLOWED_DOMAINS": str(cfg.get("auth-allowed-domains", "")),
            "TRACECAT__AUTH_MIN_PASSWORD_LENGTH": str(cfg.get("auth-min-password-length", 12)),
            "TRACECAT__DB_ENCRYPTION_KEY": self._secret_value(SECRET_DB_ENCRYPTION_KEY),
            "TRACECAT__SERVICE_KEY": self._secret_value(SECRET_SERVICE_KEY),
            "TRACECAT__SIGNING_SECRET": self._secret_value(SECRET_SIGNING_SECRET),
            "USER_AUTH_SECRET": self._secret_value(SECRET_USER_AUTH_SECRET),
            "TRACECAT__AUTH_SUPERADMIN_EMAIL": self._secret_value(SECRET_SUPERADMIN_EMAIL),
            "TRACECAT__EXECUTOR_BACKEND": "direct",
            "TRACECAT__DISABLE_NSJAIL": str(cfg.get("disable-nsjail", True)).lower(),
            "TRACECAT__EXECUTOR_CLIENT_TIMEOUT": str(cfg.get("executor-client-timeout", 300)),
            "TRACECAT__EXECUTOR_WORKER_POOL_SIZE": str(cfg.get("executor-worker-pool-size", 5)),
            # Result externalization requires S3; auto-disable when the
            # s3-credentials relation is absent so the API can start.
            "TRACECAT__RESULT_EXTERNALIZATION_ENABLED": str(
                cfg.get("result-externalization-enabled", True) and bool(self._s3_info)
            ).lower(),
            "TRACECAT__RESULT_EXTERNALIZATION_THRESHOLD_BYTES": str(
                cfg.get("result-externalization-threshold-bytes", 131072)
            ),
            "TRACECAT__COLLECTION_MANIFESTS_ENABLED": str(bool(self._s3_info)).lower(),
            "TRACECAT__WORKFLOW_ARTIFACT_RETENTION_DAYS": str(
                cfg.get("workflow-artifact-retention-days", 30)
            ),
            "TRACECAT__EE_MULTI_TENANT": str(cfg.get("multi-tenant", False)).lower(),
            "TRACECAT__CONTEXT_COMPRESSION_ENABLED": str(
                cfg.get("context-compression-enabled", False)
            ).lower(),
            "TRACECAT__CONTEXT_COMPRESSION_THRESHOLD_KB": str(
                cfg.get("context-compression-threshold-kb", 16)
            ),
            "TRACECAT__BLOB_STORAGE_BUCKET_WORKFLOW": str(
                cfg.get("blob-storage-bucket-workflow", "tracecat-workflow")
            ),
            "TRACECAT__BLOB_STORAGE_BUCKET_ATTACHMENTS": str(
                cfg.get("blob-storage-bucket-attachments", "tracecat-attachments")
            ),
            "TRACECAT__BLOB_STORAGE_BUCKET_REGISTRY": str(
                cfg.get("blob-storage-bucket-registry", "tracecat-registry")
            ),
            "TRACECAT__BLOB_STORAGE_BUCKET_AGENT": str(
                cfg.get("blob-storage-bucket-agent", "tracecat-agent")
            ),
            "TEMPORAL__CLUSTER_NAMESPACE": str(cfg.get("temporal-namespace", "default")),
            "TEMPORAL__CLUSTER_QUEUE": str(cfg.get("temporal-task-queue", "tracecat-task-queue")),
            "OIDC_SCOPES": str(cfg.get("oidc-scopes", "openid profile email")),
            "SAML_IDP_METADATA_URL": str(cfg.get("saml-idp-metadata-url", "")),
        }

        if self._db_uri:
            env["TRACECAT__DB_URI"] = self._db_uri
            env["TRACECAT__DB_SSLMODE"] = "disable"
        if self._redis_url:
            env["REDIS_URL"] = self._redis_url
        if self._temporal_url:
            env["TEMPORAL__CLUSTER_URL"] = self._temporal_url
        if dsn := cfg.get("sentry-dsn", ""):
            env["SENTRY_DSN"] = str(dsn)

        # S3 / blob storage.
        s3 = self._s3_info
        if s3:
            endpoint = s3.get("endpoint") or s3.get("endpoint-url", "")
            if endpoint:
                env["TRACECAT__BLOB_STORAGE_ENDPOINT"] = endpoint
            if s3.get("access-key"):
                env["MINIO_ROOT_USER"] = s3["access-key"]
            if s3.get("secret-key"):
                env["MINIO_ROOT_PASSWORD"] = s3["secret-key"]

        # OIDC.
        auth_types = str(cfg.get("auth-types", "basic"))
        if "oidc" in auth_types:
            env["OIDC_ISSUER"] = str(cfg.get("oidc-issuer", ""))
            env["OIDC_CLIENT_ID"] = str(cfg.get("oidc-client-id", ""))
            env["OIDC_CLIENT_SECRET"] = self._secret_value(SECRET_OIDC_CLIENT_SECRET)

        # Tracing (OTEL).
        try:
            otlp = self._tracing.otlp_grpc_endpoint() or self._tracing.otlp_http_endpoint()
            if otlp:
                env["OTEL_EXPORTER_OTLP_ENDPOINT"] = otlp
                env["OTEL_TRACES_EXPORTER"] = "otlp"
        except Exception:  # noqa: BLE001
            logger.debug("tracing endpoint not available", exc_info=True)

        # Public URLs from ingress.
        if self._ingress_url:
            env["TRACECAT__PUBLIC_API_URL"] = self._ingress_url + "/api"
            env["TRACECAT__PUBLIC_APP_URL"] = self._ingress_url
            env["TRACECAT__ALLOW_ORIGINS"] = self._ingress_url
        else:
            env["TRACECAT__PUBLIC_API_URL"] = f"http://localhost:{API_PORT}/api"
            env["TRACECAT__PUBLIC_APP_URL"] = f"http://localhost:{UI_PORT}"

        return env

    # ------------------------------------------------------------------ #
    # Pebble layers
    # ------------------------------------------------------------------ #

    def _tracecat_layer(self) -> ops.pebble.Layer:
        """Pebble layer for the tracecat container."""
        env = self._tracecat_env()
        services: dict[str, dict[str, Any]] = {
            SVC_API: {
                "override": "replace",
                "summary": "Tracecat FastAPI server",
                "command": (f"uvicorn tracecat.api.app:app --host 0.0.0.0 --port {API_PORT}"),
                "startup": "disabled",
                "working-dir": "/app",
                "environment": env,
                "on-success": "ignore",
                "on-failure": "restart",
            },
            SVC_WORKER: {
                "override": "replace",
                "summary": "Temporal workflow worker",
                "command": "python -m tracecat.dsl.worker",
                "startup": "disabled",
                "working-dir": "/app",
                "environment": env,
            },
            SVC_EXECUTOR: {
                "override": "replace",
                "summary": "Temporal activity executor",
                "command": "python -m tracecat.executor.worker",
                "startup": "disabled",
                "working-dir": "/app",
                "environment": env,
            },
        }

        # Optional AI-agent services, gated by config.
        if self.config.get("enable-agent-features", False):
            services[SVC_AGENT_WORKER] = {
                "override": "replace",
                "summary": "Temporal worker for AI agent tasks",
                "command": "python -m tracecat.agents.worker",
                "working-dir": "/app",
                "startup": "disabled",
                "environment": env,
            }
            services[SVC_AGENT_EXECUTOR] = {
                "override": "replace",
                "summary": "Temporal activity executor for AI agents",
                "working-dir": "/app",
                "command": "python -m tracecat.agents.executor",
                "startup": "disabled",
                "environment": env,
            }
            services[SVC_LITELLM] = {
                "override": "replace",
                "summary": "LiteLLM proxy",
                "command": (f"litellm --model openai/gpt-4o --port {LITELLM_PORT}"),
                "startup": "disabled",
                "working-dir": "/app",
                "environment": {
                    **env,
                    "TRACECAT__LITELLM_BASE_URL": f"http://localhost:{LITELLM_PORT}",
                },
            }
            services[SVC_MCP] = {
                "override": "replace",
                "summary": "Model Context Protocol server",
                "command": "python -m tracecat.mcp",
                "working-dir": "/app",
                "startup": "disabled",
                "environment": env,
            }

        return ops.pebble.Layer({"summary": "tracecat services", "services": services})

    def _ui_layer(self) -> ops.pebble.Layer:
        """Pebble layer for the tracecat-ui container."""
        api_url = (
            self._ingress_url + "/api" if self._ingress_url else f"http://localhost:{API_PORT}/api"
        )
        return ops.pebble.Layer(
            {
                "summary": "tracecat-ui services",
                "services": {
                    SVC_UI: {
                        "override": "replace",
                        "summary": "Tracecat Next.js frontend",
                        "command": "node server.js",
                        "startup": "enabled",
                        "environment": {
                            "NODE_ENV": "production",
                            "NEXT_PUBLIC_APP_ENV": "production",
                            "NEXT_PUBLIC_API_URL": api_url,
                            "NEXT_SERVER_API_URL": f"http://localhost:{API_PORT}",
                            "PORT": str(UI_PORT),
                        },
                    }
                },
            }
        )

    # ------------------------------------------------------------------ #
    # Startup sequence
    # ------------------------------------------------------------------ #

    def _run_migrations(self, container: ops.Container) -> bool:
        """Run Alembic migrations synchronously; return True on success.

        Uses ``container.exec`` so the hook blocks until migrations finish and
        the exit code is available. This gates ``api`` startup exactly as the
        ``migrations`` one-shot service would.
        """
        env = self._tracecat_env()
        try:
            process = container.exec(
                ["python", "-m", "alembic", "upgrade", "head"],
                environment=env,
                working_dir="/app",
                timeout=300,
            )
            process.wait_output()
            return True
        except ops.pebble.Error as exc:
            logger.error("migrations failed: %s", exc)
            return False
        except Exception:  # noqa: BLE001
            logger.exception("unexpected error running migrations")
            return False

    def _start_api(self, container: ops.Container) -> bool:
        """Start the api service and wait for the health check."""
        container.start(SVC_API)
        for _ in range(30):
            if tracecat.health_check(container):
                return True
            time.sleep(2)
        logger.error("api did not become healthy")
        return False

    def _start_core_services(self) -> None:
        """Push the layer and start api/worker/executor in order."""
        container = self.container
        if not container.can_connect():
            self.unit.status = ops.WaitingStatus("waiting for tracecat container")
            return
        container.add_layer("tracecat", self._tracecat_layer(), combine=True)

        if not self._run_migrations(container):
            self.unit.status = ops.BlockedStatus("schema migrations failed; see logs")
            return

        if not self._start_api(container):
            self.unit.status = ops.BlockedStatus("api failed health check; see logs")
            return

        # worker + executor require Temporal.
        if self._temporal_url:
            container.start(SVC_WORKER)
            container.start(SVC_EXECUTOR)
            if self.config.get("enable-agent-features", False):
                container.start(SVC_AGENT_WORKER)
                container.start(SVC_AGENT_EXECUTOR)
                container.start(SVC_LITELLM)
                container.start(SVC_MCP)

        self.unit.set_workload_version(tracecat.get_version(container) or "")
        running = ["api", "worker", "executor"] if self._temporal_url else ["api"]
        self.unit.status = ops.ActiveStatus(
            f"running: {', '.join(running)}"
            if self._temporal_url
            else "api ready; awaiting temporal"
        )

    # ------------------------------------------------------------------ #
    # Event handlers
    # ------------------------------------------------------------------ #

    def _on_install(self, _event: ops.InstallEvent) -> None:
        self._ensure_auto_secrets()
        self._reconcile(None)

    def _on_config_changed(self, _event: ops.ConfigChangedEvent) -> None:
        self._validate_config()
        self._reconcile(None)
        if self.ui_container.can_connect():
            self.ui_container.add_layer("ui", self._ui_layer(), combine=True)
            self.ui_container.replan()

    def _on_upgrade_charm(self, _event: ops.UpgradeCharmEvent) -> None:
        self._ensure_auto_secrets()
        self._reconcile(None)

    def _on_tracecat_pebble_ready(self, _event: ops.PebbleReadyEvent) -> None:
        self._reconcile(None)

    def _on_ui_pebble_ready(self, _event: ops.PebbleReadyEvent) -> None:
        if not self.ui_container.can_connect():
            return
        self.ui_container.add_layer("ui", self._ui_layer(), combine=True)
        self.ui_container.replan()

    def _on_temporal_changed(self, _event: Any) -> None:
        self._reconcile(None)

    def _on_ingress_ready(self, _event: Any) -> None:
        self._reconcile(None)
        if self.ui_container.can_connect():
            self.ui_container.add_layer("ui", self._ui_layer(), combine=True)
            self.ui_container.replan()

    def _reconcile(self, _event: Any) -> None:
        """Central reconciliation: push layer and start services when ready."""
        if not self._validate_config():
            return
        if not self._relations_ready:
            return
        self._start_core_services()

    # ------------------------------------------------------------------ #
    # Config validation
    # ------------------------------------------------------------------ #

    def _validate_config(self) -> bool:
        level = str(self.config.get("log-level", "INFO")).upper()
        if level not in VALID_LOG_LEVELS:
            self.unit.status = ops.BlockedStatus(
                f"invalid log-level {level!r}; must be one of {sorted(VALID_LOG_LEVELS)}"
            )
            return False
        auth_types = str(self.config.get("auth-types", "basic"))
        if "oidc" in auth_types:
            if not self.config.get("oidc-issuer") or not self.config.get("oidc-client-id"):
                self.unit.status = ops.BlockedStatus(
                    "oidc-issuer and oidc-client-id required when oidc in auth-types"
                )
                return False
        return True

    # ------------------------------------------------------------------ #
    # Actions
    # ------------------------------------------------------------------ #

    def _on_create_superadmin(self, event: ops.ActionEvent) -> None:
        email = self._secret_value(SECRET_SUPERADMIN_EMAIL)
        if not email:
            event.fail("tracecat-superadmin-email secret not set")
            return
        if not self.container.can_connect():
            event.fail("tracecat container not ready")
            return
        try:
            process = self.container.exec(
                [
                    "python",
                    "-c",
                    "import urllib.request, json, os;"
                    "req=urllib.request.Request('http://localhost:8000/api/auth/users/first',"
                    " data=json.dumps({'email': os.environ['TRACECAT__AUTH_SUPERADMIN_EMAIL']}).encode(),"  # noqa: E501
                    " headers={'Content-Type':'application/json'});"
                    "print(urllib.request.urlopen(req, timeout=30).read().decode())",
                ],
                environment=self._tracecat_env(),
                timeout=60,
            )
            out, _ = process.wait_output()
            logger.info("create-superadmin output: %s", out)
        except Exception as exc:  # noqa: BLE001
            event.fail(f"create-superadmin failed: {exc}")
            return
        try:
            self.container.notify("superadmin-created")
        except Exception:  # noqa: BLE001
            pass
        event.set_results({"result": "superadmin created", "email": email})

    def _on_backup(self, event: ops.ActionEvent) -> None:
        if not self._s3_info:
            event.fail("s3-credentials relation required for backup")
            return
        if not self._db_uri:
            event.fail("postgresql relation required for backup")
            return
        destination = event.params.get("destination", f"tracecat-backups/{int(time.time())}/")
        container = self.container
        if not container.can_connect():
            event.fail("tracecat container not ready")
            return
        self.unit.status = ops.MaintenanceStatus("running backup")
        try:
            container.exec(
                [
                    "pg_dump",
                    "--format=custom",
                    "--file=/tmp/tracecat.dump",
                    f"--dbname={self._db_uri}",
                ],
                timeout=300,
            ).wait_output()
        except Exception as exc:  # noqa: BLE001
            self.unit.status = ops.ActiveStatus()
            event.fail(f"pg_dump failed: {exc}")
            return
        # Upload to S3 via the mc client if present in the image, else record
        # the local dump path for the operator.
        try:
            s3 = self._s3_info
            endpoint = s3.get("endpoint", "")
            container.exec(
                [
                    "sh",
                    "-c",
                    f"mc alias set tracecat-s3 {endpoint} "
                    f"{s3.get('access-key', '')} {s3.get('secret-key', '')} "
                    "&& mc cp /tmp/tracecat.dump "
                    f"tracecat-s3/{s3.get('bucket', 'tracecat-workflow')}/{destination}tracecat.dump",  # noqa: E501
                ],
                timeout=300,
            ).wait_output()
        except Exception as exc:  # noqa: BLE001
            logger.warning("S3 upload via mc failed: %s", exc)
        self.unit.status = ops.ActiveStatus()
        event.set_results(
            {
                "backup-path": f"{destination}tracecat.dump",
                "status": "ok",
                "note": (
                    "DB encryption key is in Juju secret "
                    "tracecat-db-encryption-key; export via "
                    "`juju show-secret --reveal` before any DR scenario."
                ),
            }
        )

    def _on_restore(self, event: ops.ActionEvent) -> None:
        source = event.params.get("source", "")
        if not source:
            event.fail("source param required")
            return
        if not self._s3_info:
            event.fail("s3-credentials relation required for restore")
            return
        container = self.container
        if not container.can_connect():
            event.fail("tracecat container not ready")
            return
        self.unit.status = ops.MaintenanceStatus("restoring backup")
        for svc in (SVC_API, SVC_WORKER, SVC_EXECUTOR):
            try:
                container.stop(svc)
            except Exception:  # noqa: BLE001
                pass
        try:
            s3 = self._s3_info
            endpoint = s3.get("endpoint", "")
            container.exec(
                [
                    "sh",
                    "-c",
                    f"mc alias set tracecat-s3 {endpoint} "
                    f"{s3.get('access-key', '')} {s3.get('secret-key', '')} "
                    f"&& mc cp tracecat-s3/{s3.get('bucket', 'tracecat-workflow')}/{source} /tmp/tracecat.dump",  # noqa: E501
                ],
                timeout=300,
            ).wait_output()
            container.exec(
                [
                    "pg_restore",
                    "--dbname=" + self._db_uri,
                    "--clean",
                    "--if-exists",
                    "/tmp/tracecat.dump",
                ],
                timeout=300,
            ).wait_output()
        except Exception as exc:  # noqa: BLE001
            self.unit.status = ops.BlockedStatus(f"restore failed: {exc}")
            event.fail(f"restore failed: {exc}")
            return
        self._start_core_services()
        event.set_results({"status": "ok", "source": source})

    def _on_rotate_encryption_key(self, event: ops.ActionEvent) -> None:
        new_key = Fernet.generate_key().decode()
        old_key = self._secret_value(SECRET_DB_ENCRYPTION_KEY)
        # Re-encrypt stored integration credentials via the Tracecat CLI/API.
        container = self.container
        if container.can_connect():
            try:
                container.exec(
                    [
                        "python",
                        "-m",
                        "tracecat.cli",
                        "rotate-encryption-key",
                        "--old-key",
                        old_key,
                        "--new-key",
                        new_key,
                    ],
                    environment=self._tracecat_env(),
                    timeout=120,
                ).wait_output()
            except Exception as exc:  # noqa: BLE001
                logger.warning("in-place re-encryption failed: %s", exc)
        self._set_secret(SECRET_DB_ENCRYPTION_KEY, new_key)
        if container.can_connect():
            try:
                container.restart(SVC_API)
            except Exception:  # noqa: BLE001
                self._start_core_services()
        event.set_results({"rotated-at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})

    def _on_rotate_service_key(self, event: ops.ActionEvent) -> None:
        new_key = pysecrets.token_hex(32)
        self._set_secret(SECRET_SERVICE_KEY, new_key)
        if self.container.can_connect():
            try:
                self.container.restart(SVC_API, SVC_WORKER, SVC_EXECUTOR)
            except Exception:  # noqa: BLE001
                self._start_core_services()
        event.set_results({"result": "service key rotated"})

    def _on_rotate_signing_secret(self, event: ops.ActionEvent) -> None:
        new_secret = pysecrets.token_hex(32)
        self._set_secret(SECRET_SIGNING_SECRET, new_secret)
        if self.container.can_connect():
            try:
                self.container.restart(SVC_API)
            except Exception:  # noqa: BLE001
                self._start_core_services()
        try:
            self.container.notify("signing-secret-rotated")
        except Exception:  # noqa: BLE001
            pass
        event.set_results(
            {
                "result": "signing secret rotated",
                "warning": (
                    "All existing webhook URLs are now invalid. "
                    "Regenerate them in the Tracecat UI."
                ),
            }
        )

    def _on_upgrade_schema(self, event: ops.ActionEvent) -> None:
        container = self.container
        if not container.can_connect():
            event.fail("tracecat container not ready")
            return
        self.unit.status = ops.MaintenanceStatus("running schema upgrade")
        ok = self._run_migrations(container)
        self.unit.status = (
            ops.ActiveStatus() if ok else ops.BlockedStatus("schema upgrade failed; see logs")
        )
        if not ok:
            event.fail("schema upgrade failed")
            return
        event.set_results({"result": "schema upgraded"})

    def _on_scale_workers(self, event: ops.ActionEvent) -> None:
        pool_size = int(event.params.get("pool-size", 5))
        if not 1 <= pool_size <= 50:
            event.fail("pool-size must be between 1 and 50")
            return
        # The Pebble env is rebuilt from config on reconcile; restarting the
        # executor picks up the new TRACECAT__EXECUTOR_WORKER_POOL_SIZE.
        container = self.container
        if not container.can_connect():
            event.fail("tracecat container not ready")
            return
        # Push an updated layer with the new pool size.
        env = self._tracecat_env()
        env["TRACECAT__EXECUTOR_WORKER_POOL_SIZE"] = str(pool_size)
        layer = self._tracecat_layer()
        container.add_layer("tracecat", layer, combine=True)
        try:
            container.restart(SVC_EXECUTOR)
        except Exception as exc:  # noqa: BLE001
            event.fail(f"failed to restart executor: {exc}")
            return
        event.set_results(
            {
                "result": f"executor pool size set to {pool_size}",
                "note": (
                    "also run `juju config tracecat-k8s "
                    "executor-worker-pool-size={pool_size}` to persist"
                ),
            }
        )

    def _on_export_audit_log(self, event: ops.ActionEvent) -> None:
        since = event.params.get("since", "")
        fmt = event.params.get("format", "json")
        container = self.container
        if not container.can_connect():
            event.fail("tracecat container not ready")
            return
        try:
            query = f"?since={since}" if since else ""
            process = container.exec(
                [
                    "python",
                    "-c",
                    f"import urllib.request;"
                    f"print(urllib.request.urlopen('http://localhost:8000/api/audit{query}',"
                    f" timeout=30).read().decode())",
                ],
                environment=self._tracecat_env(),
                timeout=60,
            )
            out, _ = process.wait_output()
        except Exception as exc:  # noqa: BLE001
            event.fail(f"audit log export failed: {exc}")
            return
        content = out.decode() if isinstance(out, bytes) else str(out)
        if fmt == "csv":
            try:
                data = json.loads(content)
                rows = data if isinstance(data, list) else [data]
                if rows and isinstance(rows[0], dict):
                    import csv
                    import io

                    buf = io.StringIO()
                    writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
                    writer.writeheader()
                    writer.writerows(rows)
                    content = buf.getvalue()
            except Exception:  # noqa: BLE001
                logger.debug("csv conversion failed", exc_info=True)
        event.set_results({"log": content, "format": fmt})


if __name__ == "__main__":  # pragma: nocover
    ops.main(TracecatK8sCharm)
