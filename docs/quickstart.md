# Quick start

!!! note "Prerequisites"
    A bootstrapped Kubernetes Juju controller (`juju bootstrap microk8s
    <name>`), `juju ≥ 3.1`, `charmcraft ≥ 4.0`, and network egress to
    `ghcr.io`.

## 1. Create a model and deploy dependencies

```bash
juju add-model tracecat
juju deploy postgresql-k8s --trust
juju deploy redis-k8s
juju deploy temporal-k8s --trust
juju deploy temporal-admin-k8s --trust
juju deploy traefik-k8s --trust
juju deploy s3-integrator
```

## 2. Provide the superadmin email as a Juju secret

The initial superadmin email is **never** placed in charm config. Provide it as
a Juju secret and grant it to the charm application:

```bash
SECRET_ID=$(juju secret add superadmin-email email=ops-team@example.com)
# grant after deploying the charm (see step 3)
```

## 3. Deploy the charm

Build locally, then deploy with the workload OCI images as resources:

```bash
charmcraft pack
juju deploy ./tracecat-k8s_amd64.charm \
  --resource tracecat-image=ghcr.io/tracecathq/tracecat:1.0.0-beta.49 \
  --resource tracecat-ui-image=ghcr.io/tracecathq/tracecat-ui:1.0.0-beta.49 \
  --trust

# grant the superadmin-email secret to the charm
juju grant-secret $SECRET_ID tracecat-k8s
```

## 4. Integrate relations

```bash
juju integrate tracecat-k8s postgresql-k8s
juju integrate tracecat-k8s redis-k8s
juju integrate tracecat-k8s temporal-k8s
juju integrate tracecat-k8s traefik-k8s
juju integrate tracecat-k8s s3-integrator
juju integrate temporal-admin-k8s temporal-k8s
```

## 5. Wait for active

```bash
juju wait-for application tracecat-k8s --query='status=="active"' --timeout=10m
```

## 6. Bootstrap the superadmin

```bash
juju run tracecat-k8s/0 create-superadmin
```

## 7. Log in

Fetch the ingress URL and open it in a browser:

```bash
juju status --format=json | jq -r '.applications["traefik-k8s"].units | to_entries[0].value.address'
```

Create your first workflow with one HTTP action and trigger it manually. The run
should reach `SUCCESS` within a minute.

```text
App             Version  Status  Scale  Charm          Rev
postgresql-k8s  14.x     active      1  postgresql-k8s ...
redis-k8s                active      1  redis-k8s      ...
temporal-k8s             active      1  temporal-k8s   ...
traefik-k8s              active      1  traefik-k8s    ...
s3-integrator            active      1  s3-integrator  ...
tracecat-k8s             active      1  tracecat-k8s   ...
```
