# EasyBrowser Monorepo Migration Master

## Task

Create a new public single-repository `EasyBrowser` monorepo as a copy-only
migration target for the current `BrowserService` multi-repo workspace. The old
workspace remains read-only during the migration line. GitHub Actions will
become the primary build, test, publish, and deployment control plane, with
GHCR used for container publishing.

## Analysis Documents

- [Project Overview](../analysis/project-overview.md)
- [Module Inventory](../analysis/module-inventory.md)
- [Risk Assessment](../analysis/risk-assessment.md)

## Plan Documents

- [Task Breakdown](../plan/task-breakdown.md)
- [Dependency Graph](../plan/dependency-graph.md)
- [Milestones](../plan/milestones.md)

## Phase Summary

- [x] Phase 1: Repository Bootstrap (3/3 tasks) [details](./phase-1-repo-bootstrap.md)
- [x] Phase 2: Service Base Import (4/4 tasks) [details](./phase-2-service-base-import.md)
- [x] Phase 3: Runtime And Upstream Import (4/4 tasks) [details](./phase-3-runtime-and-upstream-import.md)
- [x] Phase 4: CI CD And Release (4/4 tasks) [details](./phase-4-ci-cd-and-release.md)
- [x] Phase 5: Public Hardening And Verification (4/4 tasks) [details](./phase-5-public-hardening-and-verification.md)

## Completion Snapshot

| Phase | Status | Completion |
| --- | --- | --- |
| Phase 1 | completed | 100% |
| Phase 2 | completed | 100% |
| Phase 3 | completed | 100% |
| Phase 4 | completed | 100% |
| Phase 5 | completed | 100% |

## Current Status

All planned migration, automation, and publication-hardening phases are
complete for the current public monorepo pass.
Active next phase: publication or follow-up refinement only if new scope is
introduced.

## Next Steps

1. Publish the repository or continue with optional refinement work.
2. Keep the old `BrowserService` workspace untouched as the migration source of
   record.
3. Use `.\scripts\test-all.ps1` before future changes.
4. Use the release checklist in `docs/release-workflow.md` before first GHCR
   publication.
