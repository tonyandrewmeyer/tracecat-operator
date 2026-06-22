# Configuration

<!-- This table is enforced against charmcraft.yaml by scripts/check-docs.py.
| Key | Type | Default | Description |
|---|---|---|---|
| `auth-types` | string | `basic` | Comma-separated list of enabled auth types: `basic`, `oidc`, `saml`. |
| `oidc-issuer` | string | ```` | OIDC issuer URL. Required when `oidc` is in `auth-types`. |
| `oidc-client-id` | string | ```` | OIDC client ID (public, non-sensitive). |
| `oidc-scopes` | string | `openid profile email` | OIDC scopes (space-separated). |
| `saml-idp-metadata-url` | string | ```` | SAML IdP metadata URL. |
| `auth-allowed-domains` | string | ```` | Comma-separated domains allowed to authenticate (empty = all). |
| `auth-min-password-length` | int | `12` | Minimum password length for basic auth. |
| `log-level` | string | `INFO` | Workload log level. One of: DEBUG, INFO, WARNING, ERROR. |
| `workflow-artifact-retention-days` | int | `30` | Days before workflow artifacts are purged. |
| `executor-worker-pool-size` | int | `5` | Executor concurrent worker count. |
| `executor-client-timeout` | int | `300` | Executor HTTP client timeout in seconds. |
| `result-externalization-enabled` | boolean | `true` | Store workflow results in S3. Requires the s3-credentials relation. |
| `result-externalization-threshold-bytes` | int | `131072` | Results larger than this (bytes) go to S3. |
| `disable-nsjail` | boolean | `true` | Disable the nsjail sandbox for the executor. Setting false requires a privileged pod. |
| `enable-agent-features` | boolean | `false` | Enable the agent-worker, agent-executor, and litellm Pebble services. |
| `multi-tenant` | boolean | `false` | Enable enterprise multi-tenancy. |
| `sentry-dsn` | string | ```` | Sentry DSN for workload error reporting (non-sensitive endpoint URL). |
| `temporal-namespace` | string | `default` | Temporal namespace for tracecat workflows. |
| `temporal-task-queue` | string | `tracecat-task-queue` | Temporal task queue name. |
| `temporal-host-override` | string | ```` | Manual Temporal host:port override. Used as a fallback when the temporal relation is absent. |
| `blob-storage-bucket-workflow` | string | `tracecat-workflow` | S3 bucket name for workflow artifacts. |
| `blob-storage-bucket-attachments` | string | `tracecat-attachments` | S3 bucket name for attachments. |
| `blob-storage-bucket-registry` | string | `tracecat-registry` | S3 bucket name for the action registry. |
| `blob-storage-bucket-agent` | string | `tracecat-agent` | S3 bucket name for agent data. |
| `context-compression-enabled` | boolean | `false` | Enable context compression. |
| `context-compression-threshold-kb` | int | `16` | Context compression threshold in KB. |


## Secrets

These are never stored in charm config. Auto-generated secrets are created on
first `install`; operator-provided secrets must be supplied via
`juju secret add` + `juju grant-secret`.

| Juju secret label | Contents | Source |
|---|---|---|
| `tracecat-db-encryption-key` | Fernet key (32-byte base64url) | Generated |
| `tracecat-service-key` | Random 32-byte hex string | Generated |
| `tracecat-signing-secret` | Random 32-byte hex string | Generated |
| `tracecat-user-auth-secret` | Random 32-byte hex string | Generated |
| `tracecat-superadmin-email` | Email string | **Operator-provided** |
| `tracecat-oidc-client-secret` | OIDC client secret | **Operator-provided** (when OIDC enabled) |

## Environment variable mapping

| Env var | Source |
|---|---|
| `TRACECAT__DB_URI` | `postgresql` relation |
| `TRACECAT__DB_ENCRYPTION_KEY` | secret `tracecat-db-encryption-key` |
| `TRACECAT__SERVICE_KEY` | secret `tracecat-service-key` |
| `TRACECAT__SIGNING_SECRET` | secret `tracecat-signing-secret` |
| `USER_AUTH_SECRET` | secret `tracecat-user-auth-secret` |
| `TEMPORAL__CLUSTER_URL` | `temporal` relation (`{host}:{port}`) |
| `TEMPORAL__CLUSTER_NAMESPACE` | `temporal-namespace` config |
| `TEMPORAL__CLUSTER_QUEUE` | `temporal-task-queue` config |
| `REDIS_URL` | `redis` relation |
| `TRACECAT__BLOB_STORAGE_ENDPOINT` | `s3-credentials` relation |
| `TRACECAT__BLOB_STORAGE_BUCKET_*` | config |
| `TRACECAT__AUTH_TYPES` | `auth-types` config |
| `OIDC_ISSUER` / `OIDC_CLIENT_ID` | config |
| `OIDC_CLIENT_SECRET` | secret `tracecat-oidc-client-secret` |
| `TRACECAT__AUTH_SUPERADMIN_EMAIL` | secret `tracecat-superadmin-email` |
| `TRACECAT__APP_ENV` | hardcoded `production` |
| `NEXT_PUBLIC_API_URL` | ingress URL (`/api` prefix) |
| `NEXT_SERVER_API_URL` | `http://localhost:8000` |
