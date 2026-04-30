# Phase 4: CI CD And Release

- [x] P4-1 Add `validate.yml` for repository validation. Acceptance criteria: pull requests can run core validation in GitHub Actions.
- [x] P4-2 Add `publish-service-base-ghcr.yml` and supporting GHCR publish flow. Acceptance criteria: tagged or manual publish path exists for the service image.
- [x] P4-3 Add root scripts for config materialization, image build, and smoke validation. Acceptance criteria: common operator workflows start from repository root.
- [x] P4-4 Document GitHub Actions secrets and release flow. Acceptance criteria: repo docs are sufficient for an operator to configure CI/CD.

## Notes

- Completed on 2026-04-30.
- Added root scripts for config init, validation, service start/probe, smoke,
  image build, config materialization, and release-tag validation.
- Added `validate.yml` and `publish-service-base-ghcr.yml`.
- Verified workflow YAML parses successfully and the local service image builds
  from `deploy/service/base/Dockerfile`.
