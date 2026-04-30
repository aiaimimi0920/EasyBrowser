# Phase 3: Runtime And Upstream Import

- [x] P3-1 Copy `repos/chrome` into `runtimes/chrome`. Acceptance criteria: self-owned Chrome runtime is present in the target repo.
- [x] P3-2 Rebind `service/base` to the new `runtimes/chrome` path. Acceptance criteria: runtime spawn/config code resolves the new path layout.
- [x] P3-3 Copy the Camoufox fork slot into `upstreams/camoufox`. Acceptance criteria: upstream area exists with clear maintenance-topology intent.
- [x] P3-4 Sanitize and copy `repos/GeekezBrowser` into `upstreams/geekez-browser`. Acceptance criteria: `node_modules/`, `out/`, and other local build outputs are excluded.

## Notes

- Completed on 2026-04-30.
- `runtimes/chrome` was imported without touching the source workspace.
- `service/base` path resolution for Chrome now points into `runtimes/chrome`.
- `upstreams/geekez-browser` was sanitized down to source-oriented content by
  removing bundled browser/runtime payloads and local build/install outputs.
