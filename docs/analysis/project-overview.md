# Project Overview

## Task Definition

- Source workspace: `C:\Users\Public\nas_home\AI\GameEditor\BrowserService`
- Target repository: `C:\Users\Public\nas_home\AI\GameEditor\EasyBrowser`
- Migration mode: copy-only
- End state: one public monorepo with GitHub Actions as the primary build,
  test, publish, and deployment control plane

## Current Source Topology

`BrowserService` is a workspace container, not a single source repository. The
workspace root holds documentation, deploy assets, and source-repository slots
under `repos/`.

Top-level source-bearing areas today:

- `repos/EasyBrowser`
  - current outward EasyBrowser service
  - Go control plane plus mixed provider/runtime assets and smoke scripts
- `repos/chrome`
  - self-owned Chrome runtime migration line
- `repos/camoufox`
  - upstream fork slot, currently placeholder-level
- `repos/GeekezBrowser`
  - upstream-tracked Electron stealth browser fork
- `deploy/EasyBrowser`
  - operator-facing build/start/probe scripts and Dockerfile
- `docs/`
  - workspace-level architecture and repository-boundary notes

## Current Technology Stack

### Control plane

- Language: Go
- Entrypoint: `repos/EasyBrowser/cmd/easybrowser/main.go`
- Primary validation command: `go test ./...` under `repos/EasyBrowser`

### Provider and runtime landscape

- Chrome runtime:
  - legacy runtime code in Python under `repos/chrome/src/browser_runtime`
  - also has a Node-based runtime adapter under `repos/EasyBrowser/providers/chrome`
- Camoufox runtime:
  - Python runtime adapter under `repos/EasyBrowser/providers/camoufox/runtime.py`
  - upstream fork slot reserved separately in `repos/camoufox`
- GeekezBrowser:
  - Electron / Node ecosystem
  - upstream fork working copy under `repos/GeekezBrowser`
- Browserbase:
  - internal provider adapter inside `repos/EasyBrowser`
  - not modeled as a top-level repo in the current source workspace

## Operational Shape

The current architecture treats EasyBrowser as an active process supervisor
rather than a passive wrapper around already-running child services.

Implemented or partially implemented behaviors include:

- public HTTP API
- browser session allocation
- provider strategy selection
- provider cooldown and health summaries
- runtime registration, heartbeat, and completion reporting
- runtime spawning in local and Docker modes

## Observed Source-Workspace Constraints

- The workspace root is not a git repository.
- `.github/workflows/` at the workspace level is effectively empty today.
- `repos/EasyBrowser` contains compiled `.exe` artifacts and should not be
  copied verbatim into a public monorepo.
- `repos/GeekezBrowser` contains `node_modules/` and `out/`, making it far too
  heavy to mirror blindly.
- Private material is intentionally kept outside source in `AIRead`, which must
  not be migrated into the public repo.

## Target Monorepo Direction

The new public repository should follow the same public-entrypoint philosophy as
`EasyEmail`:

- one repository for contributors
- one root config model
- clear maintenance-topology boundaries
- root-level scripts for common operator flows
- GitHub Actions-owned validation and publish workflows

Recommended target layout:

```text
service/
  base/
runtimes/
  chrome/
upstreams/
  camoufox/
  geekez-browser/
deploy/
  service/
    base/
docs/
scripts/
.github/
  workflows/
```

### Boundary rules in the target repo

- `service/base`
  - copied from `repos/EasyBrowser`
  - Browserbase remains an internal provider here
- `runtimes/chrome`
  - copied from `repos/chrome`
  - self-owned runtime, so it does not belong under `upstreams/`
- `upstreams/camoufox`
  - copied from the fork slot in `repos/camoufox`
- `upstreams/geekez-browser`
  - copied from `repos/GeekezBrowser`
  - sanitized import only
- `deploy/service/base`
  - copied from `deploy/EasyBrowser`

## Immediate Planning Outcome

Before importing source code, the target repo needs:

- planning docs
- progress tracking
- root ignore policy
- target directory skeleton
- a task list for code import, sanitization, CI, and GHCR publish wiring
