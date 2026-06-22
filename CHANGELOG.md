# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Initial Juju K8s charm for Tracecat (`tracecat-k8s`).
- Two-container workload: `tracecat` (API, workers, executor) and `tracecat-ui`
  (Next.js frontend).
- Relations: `postgresql`, `redis`, `temporal`, `ingress` (traefik), `s3-credentials`,
  `certificates` (TLS), `logging` (Loki), `metrics-endpoint` (Prometheus),
  `grafana-dashboard`, `tracing` (Tempo).
- Pebble services: `migrations` (oneshot), `api`, `worker`, `executor`, and
  optional `agent-worker`, `agent-executor`, `litellm`, `mcp`.
- Day-2 actions: `create-superadmin`, `backup`, `restore`,
  `rotate-encryption-key`, `rotate-service-key`, `rotate-signing-secret`,
  `scale-workers`, `export-audit-log`, `upgrade-schema`.
- Juju secrets surface for all credentials (db encryption key, service key,
  signing secret, user-auth secret, superadmin email, OIDC client secret).
- COS-Lite observability: Loki log forwarding, Prometheus metrics, Tempo
  tracing, shipped Grafana dashboard and alert rules.
- mkdocs-material documentation site; `scripts/check-docs.py` keeps the
  configuration page in sync with `charmcraft.yaml`.
- GitHub Actions: CI (lint + unit tests), integration tests on main,
  release-please, security scanning (zizmor + dependency-review), docs deploy,
  Charmhub upload (upload-only).

[Unreleased]: https://github.com/tonyandrewmeyer/tracecat-operator/compare/HEAD
