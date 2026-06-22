---
name: Bug report
about: Report a problem with the tracecat-k8s charm
title: "[bug] "
labels: bug
---

## Environment

- **Tracecat version (workload image tag):**
- **Charm revision:** `juju status tracecat-k8s` (Revision line)
- **Juju version:** `juju version`
- **Kubernetes flavour:** (microk8s / Canonical Kubernetes / other)
- **Charm config:** `juju config tracecat-k8s` (redact secrets)

## What happened

<!-- A clear description of what went wrong. -->

## What I expected

<!-- What you expected to happen instead. -->

## Reproduction steps

1.
2.
3.

## Relevant output

```
# juju status --relations
# juju debug-log --replay --include tracecat-k8s/0 | tail -100
```
