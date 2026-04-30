# Phase 2: Service Base Import

- [x] P2-1 Copy `BrowserService\repos\EasyBrowser` into `service/base`. Acceptance criteria: target import exists; source repo is unchanged.
- [x] P2-2 Remove generated binaries, logs, and local-only artifacts from the imported target tree. Acceptance criteria: no compiled `.exe` outputs remain tracked in the public repo.
- [x] P2-3 Rewrite path assumptions so `service/base` resolves runtimes and deploy assets in the new monorepo. Acceptance criteria: old BrowserService-relative paths are removed or redirected.
- [x] P2-4 Relocate service docs, Docker assets, and smoke helpers coherently in the new layout. Acceptance criteria: source layout is understandable without the old workspace.

## Notes

- Completed on 2026-04-30.
- `service/base` was imported and cleaned in the target repo only.
- `go test ./...` passed in the imported `service/base`.
- `deploy/service/base/scripts/start-easybrowser.ps1` successfully started the
  service and `/healthz` responded as expected.
