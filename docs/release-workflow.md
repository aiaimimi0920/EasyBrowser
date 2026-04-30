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
6. Optionally upload rendered runtime artifacts to private R2
7. Optionally generate an encrypted owner-only import-code artifact

The GHCR publish path remains valid even when the R2/import-code secrets are not
configured. In that case the workflow skips the distribution steps but still
publishes the image.

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
- if using private R2 distribution, ensure all `EASYBROWSER_R2_CONFIG_*`
  secrets are configured
- if using encrypted import-code output, ensure
  `EASYBROWSER_IMPORT_CODE_OWNER_PUBLIC_KEY` is configured
- push a tag matching `v*`, `release-*`, or `service-base-*`, or trigger the
  publish workflow manually
