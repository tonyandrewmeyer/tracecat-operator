## Summary

<!-- One-line description of the change. -->

## Checklist

- [ ] Conventional commit used (`feat:`, `fix:`, `docs:`, …)
- [ ] `uv run pre-commit run --all-files` passes (ruff, mypy, yamllint, actionlint)
- [ ] `uv run pytest tests/unit` passes
- [ ] Unit tests added/updated for changed behaviour
- [ ] `CHANGELOG.md` `[Unreleased]` updated (if user-facing)
- [ ] `docs/configuration.md` regenerated via `scripts/check-docs.py` (if config changed)
- [ ] `juju status` output attached (if integration-relevant)
- [ ] No secret value added to `config:` or committed
