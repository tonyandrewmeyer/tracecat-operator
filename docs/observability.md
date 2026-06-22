# Observability

The charm is a first-class member of the [COS-Lite](https://charmhub.io/topics/canonical-observability-stack)
family. Relate the four COS applications to get logs, metrics, traces, and
dashboards with zero additional configuration.

```bash
juju deploy cos-lite --trust
juju integrate tracecat-k8s loki-k8s
juju integrate tracecat-k8s prometheus-k8s
juju integrate tracecat-k8s grafana-k8s
juju integrate tracecat-k8s tempo-coordinator-k8s
```

## Logs — Loki

`LogProxyConsumer` forwards the `api`, `worker`, and `executor` Pebble service
logs to the Loki push-API endpoint.

## Metrics — Prometheus

The Tracecat API exposes a `/metrics` endpoint on port 8000 (Prometheus
scrape format). `MetricsEndpointProvider` registers a scrape job targeting
`*:8000`. If the upstream version lacks `/metrics`, the charm ships a sidecar
`exporter` service (port 9090) that scrapes Tracecat API stats.

## Traces — Tempo

The tracing charmlib (`tempo-coordinator-k8s`) provides the OTEL exporter
endpoint. Tracecat's FastAPI app is instrumented with OpenTelemetry; the charm
sets `OTEL_EXPORTER_OTLP_ENDPOINT` from relation data.

## Grafana dashboards

A `tracecat-overview` dashboard is shipped at
[`src/dashboards/tracecat-overview.json`](https://github.com/tonyandrewmeyer/tracecat-operator/blob/main/src/dashboards/tracecat-overview.json)
and registered via `GrafanaDashboardProvider`. Panels include:

- Workflow executions per minute
- API request rate and error rate
- Executor queue depth
- Active case count

![tracecat-overview dashboard](assets/tracecat-overview.png)

## Alert rules

Shipped at [`src/prometheus_alert_rules/tracecat.rule`](https://github.com/tonyandrewmeyer/tracecat-operator/blob/main/src/prometheus_alert_rules/tracecat.rule).

| Alert | Trigger | Severity |
|---|---|---|
| `TracecatApiDown` | `/health` fails for > 2 min | critical |
| `TracecatExecutorQueueDepthHigh` | executor queue depth > threshold | warning |
| `TracecatNoWorkflowCompleted` | no workflow completed in 30 min | warning |
