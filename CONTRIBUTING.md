# Contributing

EasyBrowser is maintained as a single public monorepo so contributors do not
need to discover or coordinate across multiple repositories.

## Basic workflow

1. Fork this repository.
2. Create a branch for your change.
3. Run `.\scripts\test-all.ps1` before opening a pull request.
4. Keep changes scoped to the correct top-level area:
   - `service/base` for control-plane code
   - `runtimes/chrome` for self-owned Chrome runtime code
   - `upstreams/*` for upstream-tracked code
   - `deploy/service/base` for deploy assets
   - `docs` for repository-level contributor/operator docs
5. Do not commit local config, generated binaries, caches, or installed browser
   payloads.

## Boundary rules

- `service/base` owns the public EasyBrowser API boundary.
- `runtimes/chrome` is self-owned runtime code.
- `upstreams/camoufox` and `upstreams/geekez-browser` preserve upstream
  topology and should not be casually rewritten into internal modules.
- Public-repo cleanup belongs in this repository, never in the legacy
  BrowserService source workspace.
