# Relations

The charm is stateless; all persistent state lives in relations. Each relation
maps to a Juju interface consumed via the published charmlib.

## PostgreSQL — `postgresql_client`

**Why:** Tracecat application database. PostgreSQL 16 compatible.

```bash
juju deploy postgresql-k8s --trust
juju integrate tracecat-k8s postgresql-k8s
```

**Broken relation:** the charm sets `blocked` (DB required); `api`, `worker`,
`executor` stop.

## Redis — `redis`

**Why:** sessions and caching.

```bash
juju deploy redis-k8s
juju integrate tracecat-k8s redis-k8s
```

**Broken relation:** charm sets `waiting`; `api` cannot serve authenticated
requests.

## Temporal — `temporal-host-info`

**Why:** durable workflow execution engine. Without Temporal, workflows cannot
run (only the API/UI are usable).

```bash
juju deploy temporal-k8s --trust
juju deploy temporal-admin-k8s --trust
juju integrate tracecat-k8s temporal-k8s
juju integrate temporal-admin-k8s temporal-k8s
```

`temporal-k8s` requires its own PostgreSQL:

```bash
juju deploy postgresql-k8s temporal-db --trust
juju integrate temporal-k8s temporal-db
```

**Broken relation:** `worker` and `executor` services stop; the API remains up
but workflow execution fails.

## Ingress — `ingress`

**Why:** HTTP ingress and public URL. Provided by `traefik-k8s`.

```bash
juju deploy traefik-k8s --trust
juju integrate tracecat-k8s traefik-k8s
```

On `ingress_ready`, the charm updates `NEXT_PUBLIC_API_URL` (UI) and
`TRACECAT__PUBLIC_API_URL` / `TRACECAT__PUBLIC_APP_URL` (API), then restarts the
relevant services.

## S3 — `s3`

**Why:** workflow artifacts, attachments, action registry, agent filesystem.
Required for result externalization and the `backup`/`restore` actions.

```bash
juju deploy s3-integrator
juju config s3-integrator endpoint=http://minio.default.svc:9000 \
  bucket=tracecat-workflow path=/ region=us-east-1
juju integrate tracecat-k8s s3-integrator
```

**Broken relation:** result externalization degrades; new workflow artifacts
cannot be stored; `backup`/`restore` actions error.

## Certificates — `tls-certificates`

**Why:** HTTPS termination for the API/UI.

```bash
juju deploy self-signed-certificates
juju integrate tracecat-k8s self-signed-certificates
```

## COS-Lite — observability

See [Observability](observability.md).

| Relation | Interface | Charm |
|---|---|---|
| `logging` | `loki_push_api` | `loki-k8s` |
| `metrics-endpoint` | `prometheus_scrape` | `prometheus-k8s` |
| `grafana-dashboard` | `grafana_dashboard` | `grafana-k8s` |
| `tracing` | `tracing` | `tempo-coordinator-k8s` |
