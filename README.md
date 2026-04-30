# EasyBrowser

EasyBrowser is the public monorepo entrypoint for the BrowserService ecosystem.

This repository was created as a copy-only migration target from the internal
multi-repository `BrowserService` workspace. The legacy workspace remains the
source archive for migration comparison, while all public-repository
restructuring, CI/CD, and contributor ergonomics now live here.

## Repository Layout

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

## Module Roles

### `service/base`

The EasyBrowser control plane.

Responsibilities:

- public/admin/internal HTTP API
- browser session allocation
- provider strategy, cooldown, and telemetry
- runtime registration and child-process supervision
- internal Browserbase provider adapter

### `runtimes/chrome`

The self-owned Chrome runtime copied from the legacy BrowserService workspace.

Responsibilities:

- local Chrome bootstrap
- stealth/profile/proxy helpers
- browser-local runtime behavior used by the control plane

### `upstreams/camoufox`

The upstream-tracked Camoufox fork slot.

This area is classified as `upstreams/` because its maintenance topology is
upstream-oriented even though it participates in runtime execution.

### `upstreams/geekez-browser`

The upstream-tracked GeekezBrowser fork.

The public monorepo intentionally excludes heavy local build/install artifacts
such as bundled browsers and `node_modules/`. Run the upstream setup flow from
source when those runtime assets are needed locally.

### `deploy/service/base`

Deployment-side assets for the EasyBrowser control plane.

Responsibilities:

- service image Dockerfile
- start/probe/smoke helpers
- environment templates

## Quick Start

### 1. Initialize local config

```powershell
.\scripts\init-config.ps1
```

### 2. Validate the repository

```powershell
.\scripts\test-all.ps1
```

### 3. Start the service locally

```powershell
.\scripts\start-service-base.ps1
```

### 4. Probe the running service

```powershell
.\scripts\probe-service-base.ps1
```

## Toolchain

- Go `1.26+` for `service/base`
- Python `3.12+` for helper scripts and provider runtimes
- Node.js `20.x` for repository-wide JS tooling and upstream modules

The repository root includes `.nvmrc` and `.node-version` to pin the shared
Node baseline.

## GitHub Actions

Workflows live under `.github/workflows/`:

- `validate.yml`
  - root repository validation for pull requests and `main`
- `publish-service-base-ghcr.yml`
  - GHCR image publish flow for the control plane

## Configuration

Copy `config.example.yaml` to `config.yaml` for local operator use.

The root config is intentionally the contributor/operator entrypoint. It is
used for hosted workflow materialization and local script defaults.

See:

- `docs/architecture.md`
- `docs/quickstart.md`
- `docs/configuration.md`
- `docs/github-actions-secrets.md`
- `docs/release-workflow.md`
- `docs/migration-audit.md`

## Migration Rules

- Treat `C:\Users\Public\nas_home\AI\GameEditor\BrowserService` as the read-only
  source workspace during this migration line.
- Do not delete, rewrite, or reorder files in the old workspace while
  restructuring this public repo.
- Perform all cleanup and path rewrites only in this target repository.
