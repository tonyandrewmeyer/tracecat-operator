# Day-2 operations

## Backup

The `backup` action takes a PostgreSQL `pg_dump` (custom format) and uploads it
to S3 alongside a snapshot of workflow artifacts.

```bash
juju run tracecat-k8s/0 backup destination=tracecat-backups/2026-06-22/
```

!!! warning "Encryption key"
    The DB encryption key (`tracecat-db-encryption-key` secret) is **not**
    included in the backup. Export it separately for DR:

    ```bash
    juju show-secret tracecat-db-encryption-key --reveal
    ```

    Without this key, a restored database cannot be decrypted.

### Scheduled backups

Schedule via Juju action cron (e.g. a `systemd` timer on the operator, or a
Juju `juju run` wrapped by a cron job):

```cron
0 2 * * *  juju run tracecat-k8s/0 backup destination=tracecat-backups/$(date +\%F)/
```

## Restore

```bash
juju run tracecat-k8s/0 restore source=tracecat-backups/2026-06-22/
```

The charm sets `maintenance`, stops `api`/`worker`/`executor`, downloads the
dump, runs `pg_restore`, restarts services, and waits for the health check
before returning to `active`.

Ensure the `tracecat-db-encryption-key` secret matches the key in effect when
the backup was taken.

## Schema upgrade

Alembic migrations run automatically as a Pebble one-shot (`migrations` service)
before `api` starts. On `juju refresh` the charm re-runs migrations.

Run migrations manually (e.g. to apply a pending migration without a refresh):

```bash
juju run tracecat-k8s/0 upgrade-schema
```

## Secret rotation

| Secret | Recommended cadence | Action |
|---|---|---|
| `tracecat-db-encryption-key` | Annually | `rotate-encryption-key` (re-encrypts stored credentials; brief read-only window) |
| `tracecat-service-key` | Quarterly | `rotate-service-key` (restarts all services) |
| `tracecat-signing-secret` | On suspected compromise | `rotate-signing-secret` (**invalidates all existing webhook URLs** — regenerate them) |

## Multi-tenancy

Enable enterprise multi-tenancy:

```bash
juju config tracecat-k8s multi-tenant=true
```

!!! note
    Multi-tenancy is a Tracecat Enterprise feature and may require a licence
    key. Enabling it without a licence may gate functionality upstream.

## Audit log export

```bash
# JSON (default)
juju run tracecat-k8s/0 export-audit-log since=2026-06-01T00:00:00Z
# CSV
juju run tracecat-k8s/0 export-audit-log since=2026-06-01T00:00:00Z format=csv
```

For large result sets the action writes to S3 and returns the object path.

## Temporal deployment notes

The charm consumes Temporal connection details from the `temporal-host-info`
relation (the `temporal-k8s` charm). If `temporal-k8s` cannot be deployed, set
a manual override:

```bash
juju config tracecat-k8s temporal-host-override=temporal.default.svc:7233
```

A manual fallback manifest is provided at
[`hack/temporal-k8s-manual.yaml`](https://github.com/tonyandrewmeyer/tracecat-operator/blob/main/hack/temporal-k8s-manual.yaml)
deploying `temporalio/auto-setup:1.27.1`.

## Disaster recovery posture

Recommended DR combines:

1. **Juju model backup** — `juju create-backup` on the controller.
2. **PostgreSQL dump** — the `backup` action.
3. **S3 bucket versioning** — enable versioning on the object storage bucket so
   artifact/attachment history is recoverable.
4. **Encryption key** — export `tracecat-db-encryption-key` to a secure vault;
   it is the single most critical secret for recovery.
