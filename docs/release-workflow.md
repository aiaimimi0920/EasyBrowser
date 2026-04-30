# Release Workflow

## Validation

Before publishing, run:

```powershell
.\scripts\test-all.ps1
```

## Supported Tag Shapes

The current service-image release workflow accepts these tag prefixes:

- `v*`
- `release-*`
- `service-base-*`

Validation is enforced by:

- `scripts/validate-release-tag.py`
- `.github/workflows/publish-service-base-ghcr.yml`

## Hosted Publish

Push a matching tag or trigger the workflow manually:

- `.github/workflows/publish-service-base-ghcr.yml`

Current publish flow:

1. Check out repository
2. Materialize `config.yaml` from the example plus optional env overlays
3. Validate the release tag
4. Optionally run a local smoke image build and `/healthz` check
5. Publish the `service/base` image to GHCR

## Current Image Target

The first hosted release path publishes the EasyBrowser control-plane image.

Runtime-specific images can be added later once contributor workflow for the
Chrome/Camoufox/Geekez runtime subtrees is stabilized.

## First Publish Checklist

- run `.\scripts\test-all.ps1`
- confirm `docs/migration-audit.md` still matches the imported tree
- confirm no generated binaries, install outputs, or local-only secrets are
  present in the repo
- ensure the repository has the desired owner namespace before publishing GHCR
  tags
- push a tag matching `v*`, `release-*`, or `service-base-*`, or trigger the
  publish workflow manually
