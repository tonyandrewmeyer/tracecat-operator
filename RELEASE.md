# Release process

This document describes how a publisher promotes a `tracecat-k8s` revision
from the upload-only state to a public Charmhub channel.

## Prerequisites

- The charm name `tracecat-k8s` is registered on Charmhub
  (https://charmhub.io/register-charm).
- `CHARMHUB_TOKEN` is set in the GitHub repository secrets (used by the
  `.github/workflows/charmhub-upload.yml` workflow).
- Charmcraft is installed locally: `sudo snap install charmcraft --classic`.

## 1. Cut a release tag

Releases are automated via [release-please](https://github.com/googleapis/release-please).
A push to `main` that includes Conventional Commits of type `feat:`/`fix:`
triggers release-please to open a release PR. Merging that PR tags the release
and pushes the tag.

To cut a release manually:

```bash
git tag -a 0.1.0 -m "chore(release): 0.1.0 — first production-ready release"
git push origin 0.1.0
```

## 2. Upload (automatic)

The tag push triggers the `Charmhub upload` workflow, which packs the charm
and uploads it as a **new revision** under `latest/edge` (upload-only; not yet
released to a public channel).

Verify the revision appears:

```bash
charmcraft status tracecat-k8s
charmcraft revisions tracecat-k8s
```

## 3. Promote to a channel

Promotion is a deliberate, manual step. Once a revision has been tested
(integration tests green, smoke-tested on a staging model):

```bash
# From latest/edge to candidate
charmcraft release tracecat-k8s --revision=<N> --channel=1.0/candidate

# After candidate soak, promote to stable
charmcraft release tracecat-k8s --revision=<N> --channel=1.0/stable
```

Or, if the upload workflow's `track:` line is uncommented, the upload itself
releases to the configured channel — only do this once the track is stable.

## 4. Update CHANGELOG

`release-please` maintains `CHANGELOG.md` automatically from Conventional
Commits. For manual releases, add an entry under the new version following the
[Keep a Changelog](https://keepachangelog.com) format.

## 5. OCI image resources

The workload OCI images (`tracecat-image`, `tracecat-ui-image`) are NOT
uploaded as Charmhub resources by default — the charm references them by
`upstream-source` (ghcr.io). Operators deploy with `--resource` overrides only
when pinning a different tag. If offline/air-gapped deployment is required,
upload the images as resources:

```bash
charmcraft upload-resource tracecat-k8s tracecat-image --image=ghcr.io/tracecathq/tracecat:1.0.0-beta.49
```
