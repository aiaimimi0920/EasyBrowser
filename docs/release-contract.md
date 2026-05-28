# Release Contract

Project: `EasyBrowser`

Release class: `standard-service-base`

This repository follows the EasyAiMi release contract v1. The contract standardizes the operator-facing behavior of GitHub Actions, GHCR images, R2 config distribution, encrypted import-code artifacts, and blank-host local deployment. Project-specific build internals are allowed when the public contract remains stable.

## Standard guarantees

- Manual publish workflows accept a standard `release_tag` override. Legacy `version` inputs remain supported where they already existed.
- Publish metadata writes both `release_tag` and `version` outputs when the workflow has a release metadata step.
- Config-bearing releases publish an R2 distribution manifest artifact and an encrypted owner import-code artifact.
- Local deployment starts from `deploy-host.ps1` and must support an empty host directory using GHCR images plus an import code.
- Deployment logic must not depend on bind mounting `C:\Users\Public\nas_home\AI\GameEditor\<Project>` source trees.

## Workflows

| Component | Workflow | Tag inputs | Required artifacts | Required capabilities |
| --- | --- | --- | --- | --- |
| `service-base` | `.github/workflows/publish-service-base-ghcr.yml` | `release_tag, version` | `easybrowser-r2-manifest, easybrowser-import-code-encrypted, service-base-r2-config-manifest, service-base-import-code-encrypted` | GHCR, R2, import-code |

## Project-specific exceptions

- Keeps legacy EasyBrowser artifact names while also uploading standard service-base aliases.

## Verification

Run this contract check from the repository root:

```powershell
python scripts/validate-release-contract.py
```

The check is intentionally textual. It verifies the workflow contract, artifact names, release tag aliases, the local deploy entrypoint, and this document without requiring live GitHub, GHCR, or R2 access.
