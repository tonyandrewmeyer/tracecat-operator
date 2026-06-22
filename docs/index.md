# tracecat-operator

Juju charm for [Tracecat](https://github.com/TracecatHQ/tracecat), an
open-source, AI-native security orchestration, automation, and response (SOAR)
platform with durable workflow execution powered by Temporal.

## What is Tracecat?

Tracecat is an open-source SOAR platform that lets security teams build, run,
and automate detection-and-response workflows. Workflows are durable Temporal
workflows composed of composable actions, with a no-code visual builder and a
Python-first registry for custom integrations.

## What this charm does

The `tracecat-k8s` charm deploys and operates Tracecat on Kubernetes (MicroK8s
or Canonical Kubernetes) using Juju. It runs two OCI containers:

- **`tracecat`** — the FastAPI server, Temporal workflow workers, and the
  activity executor (plus optional AI-agent services), all from
  `ghcr.io/tracecathq/tracecat`.
- **`tracecat-ui`** — the Next.js frontend from
  `ghcr.io/tracecathq/tracecat-ui`.

State lives entirely in relations: PostgreSQL (app DB), Redis (sessions/cache),
Temporal (workflow engine), and S3 (artifacts/attachments/registry). The charm
itself is stateless; all credentials are Juju secrets.

## Licence

The charm operator code is **Apache 2.0**; the deployed Tracecat workload is
**AGPL-3.0**. See [`CONTRIBUTING.md`](https://github.com/tonyandrewmeyer/tracecat-operator/blob/main/CONTRIBUTING.md).

Head to the [Quick start](quickstart.md) to deploy your first workflow.
