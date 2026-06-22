# Contributing to tracecat-operator

Thanks for your interest in contributing! This document covers the development
workflow for the **tracecat-k8s** Juju charm.

## Licence

The charm (operator) code in this repository is licensed under
**Apache 2.0** (see [`LICENSE`](./LICENSE)). The upstream **Tracecat workload**
it deploys is licensed under **AGPL-3.0** — these are different licences and
the charm code is not derived from the workload source. By contributing you
agree your contributions are licensed under Apache 2.0.

## Development setup

This project uses [`uv`](https://docs.astral.sh/uv/) for Python dependency
management and [`charmcraft`](https://documentation.ubuntu.com/charmcraft/) for
building the charm.

```bash
# Install uv (if not present)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies (locked)
uv sync --all-extras

# Install pre-commit hooks
uv run pre-commit install
```

Requirements: Python ≥ 3.12, charmcraft ≥ 4.0, juju ≥ 3.1.

## Running tests

### Unit tests

Unit tests use `ops.testing.Harness` (no Juju required):

```bash
uv run pytest tests/unit -v
```

### Integration tests

Integration tests use [`jubilant`](https://github.com/canonical/jubilant) and
require a bootstrapped Kubernetes Juju controller:

```bash
juju switch <your-k8s-controller>
uv run pytest tests/integration -v
```

Integration tests spin up a temporary Juju model, deploy all required charms
(postgresql-k8s, redis-k8s, temporal-k8s, traefik-k8s, s3-integrator), and
tear it down on completion.

## Conventional Commits

We use [Conventional Commits](https://www.conventionalcommits.org/) —
`release-please` generates the changelog and GitHub releases from them.

Common prefixes: `feat:`, `fix:`, `docs:`, `test:`, `chore:`, `refactor:`,
`ci:`. Scope examples: `feat(charm):`, `test(integration):`, `docs:`.

Commits land directly on `main` unless a PR workflow is explicitly requested.

## Pull requests

1. Rebase on `main` before opening.
2. Ensure `uv run pre-commit run --all-files` passes (ruff, mypy, yamllint,
   actionlint).
3. Ensure `uv run pytest tests/unit` passes.
4. Update `CHANGELOG.md` under `[Unreleased]` if user-facing.
5. Attach `juju status` output if the change is integration-relevant.
6. Reference any related issue (`Closes #N`).

## Charm conventions

- **Charm libraries over hand-rolled requirers.** Import published charmlibs
  for relation interfaces; only hand-roll when no library exists.
- **Juju secrets for every credential.** No password, key, or token in
  `config:`.
- **`ops.testing.Harness` for unit tests; `jubilant` for integration.** Do not
  use `pytest-operator`.
- **`charmcraft 4.x` + `ops 3.x`.**

## Building the charm

```bash
charmcraft pack
ls -la *.charm
```
