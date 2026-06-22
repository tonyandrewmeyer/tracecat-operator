# tracecat-operator

[![CI](https://github.com/tonyandrewmeyer/tracecat-operator/actions/workflows/ci.yml/badge.svg)](https://github.com/tonyandrewmeyer/tracecat-operator/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](./LICENSE)

Juju charm for [Tracecat](https://github.com/TracecatHQ/tracecat), an
open-source security orchestration, automation, and response (SOAR) platform
with durable workflow execution via Temporal.

> **Licence:** the charm operator code is **Apache 2.0**; the deployed Tracecat
> workload is **AGPL-3.0**. See [`CONTRIBUTING.md`](./CONTRIBUTING.md).

## What is Tracecat?

Tracecat is an open-source, AI-native SOAR platform that lets security teams
build, run, and automate detection-and-response workflows. Workflows are
durable Temporal workflows composed of composable actions, with a no-code
visual builder and a Python-first registry for custom integrations.

## Quick start

```bash
# Bootstrap a k8s controller (once)
juju bootstrap microk8s <controller-name>

juju add-model tracecat
juju deploy postgresql-k8s --trust
juju deploy redis-k8s
juju deploy temporal-k8s --trust
juju deploy traefik-k8s --trust
juju deploy s3-integrator

# Provide the superadmin email as a Juju secret
juju secret add superadmin-email email=ops-team@example.com

# Deploy the charm
juju deploy ./tracecat-k8s_amd64.charm \
  --resource tracecat-image=ghcr.io/tracecathq/tracecat:1.0.0-beta.49 \
  --resource tracecat-ui-image=ghcr.io/tracecathq/tracecat-ui:1.0.0-beta.49 \
  --trust

juju integrate tracecat-k8s postgresql-k8s
juju integrate tracecat-k8s redis-k8s
juju integrate tracecat-k8s temporal-k8s
juju integrate tracecat-k8s traefik-k8s
juju integrate tracecat-k8s s3-integrator

# Bootstrap the superadmin account
juju run tracecat-k8s/0 create-superadmin
```

See the [Quick start guide](https://tonyandrewmeyer.github.io/tracecat-operator/quickstart/)
for a full walkthrough.

## Relation matrix

| Relation | Interface | Required | Purpose |
|---|---|---|---|
| `postgresql` | `postgresql_client` | yes | Application database (PostgreSQL 16) |
| `redis` | `redis` | yes | Sessions, caching |
| `temporal` | `temporal-host-info` | yes | Durable workflow execution engine |
| `ingress` | `ingress` | yes | HTTP ingress (traefik-k8s) |
| `s3-credentials` | `s3` | yes | Workflow artifacts, attachments, action registry |
| `certificates` | `tls-certificates` | no | HTTPS termination |
| `logging` | `loki_push_api` | no | Workload log forwarding (COS-Lite) |
| `metrics-endpoint` | `prometheus_scrape` | no | Metrics (COS-Lite) |
| `grafana-dashboard` | `grafana_dashboard` | no | Shipped dashboards (COS-Lite) |
| `tracing` | `tracing` | no | Distributed traces (Tempo) |

## Day-2 operations

| Action | Description |
|---|---|
| `create-superadmin` | Bootstrap the initial superadmin workspace. |
| `backup` | PostgreSQL `pg_dump` + S3 artifact snapshot. |
| `restore` | Restore from a backup snapshot. |
| `rotate-encryption-key` | Rotate the DB encryption key; re-encrypts stored credentials. |
| `rotate-service-key` | Rotate the service-to-service auth key. |
| `rotate-signing-secret` | Rotate the webhook signing secret (invalidates existing webhooks). |
| `scale-workers` | Adjust executor worker pool size without a charm upgrade. |
| `export-audit-log` | Export audit log entries (JSON/CSV). |
| `upgrade-schema` | Run Alembic migrations manually. |

See [Day-2 operations](https://tonyandrewmeyer.github.io/tracecat-operator/day2-ops/).

## Observability

The charm is a first-class citizen of the COS-Lite (Canonical Observability
Stack) family. Relate `loki-k8s` for logs, `prometheus-k8s` for metrics,
`grafana-k8s` for the shipped Tracecat overview dashboard, and
`tempo-coordinator-k8s` for distributed traces. A Grafana dashboard and three
Prometheus alert rules are shipped with the charm. See
[Observability](https://tonyandrewmeyer.github.io/tracecat-operator/observability/).

## Contributing

See [`CONTRIBUTING.md`](./CONTRIBUTING.md).
