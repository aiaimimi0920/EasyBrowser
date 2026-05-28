# EasyBrowser

EasyBrowser is the public monorepo entrypoint for the BrowserService ecosystem.

This repository was created as a copy-only migration target from the internal
multi-repository `BrowserService` workspace. The legacy workspace remains the
source archive for migration comparison, while all public-repository
restructuring, CI/CD, and contributor ergonomics now live here.

## Development Workflow

See `docs/development-workflow.md` for the shared cross-repository development
rules used for local-first iteration, temporary test assets, and final
GHCR-based validation.

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
- runtime registration, child-process supervision, and dynamic runtime pooling
- internal Browserbase provider adapter

The intended runtime model is:

- `service/base` is the planning and manager layer
- provider runtimes are child executors owned by the manager
- the manager may keep a small warm set of idle executors
- task pressure can grow the pool dynamically
- idle surplus executors are reaped automatically

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

The repository root now includes a host-facing one-click deploy wrapper:

```powershell
pwsh .\deploy-host.ps1
```

You can also download only `deploy-host.ps1` from GitHub and run it on a blank
host. The script bootstraps a local repo cache automatically before invoking
the canonical deployment path.

The same root entrypoint now also supports owner-only runtime bootstrap
through either:

- `-ImportCode <decrypted-import-code>`
- `-BootstrapFile <r2-bootstrap.json>`

If you keep the owner private key as a stable passphrase string instead of a
raw base64 private key, derive the matching public key with:

```powershell
python .\scripts\easybrowser-import-code.py derive-public-key --private-key-file .\owner-private-key.txt
```

That root entrypoint now deploys the Dockerized `service/base` control plane
and does three things in order:

- creates `config.yaml` from `config.example.yaml` when it is missing
- renders `deploy/service/base/.env.local` from the root config
- forwards into `scripts/deploy-service-base.ps1`

The rendered runtime env now also carries the runtime-pool policy, including:

- `EASYBROWSER_RUNTIME_POOL_ENABLED`
- `EASYBROWSER_RUNTIME_POOL_RECONCILE_SECONDS`
- `EASYBROWSER_RUNTIME_POOL_IDLE_TIMEOUT_SECONDS`
- per-provider warm floor such as `EASYBROWSER_CHROME_MIN_WARM`

The lower-level Docker deploy entrypoint is still available:

```powershell
pwsh .\scripts\deploy-service-base.ps1
```

The local process helper is still kept for development-only runs:

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
- `docs/root-host-deploy-standard.md`

## Root Operator Entry

- `deploy-host.ps1`
  - repository-root host wrapper for Docker deployment
  - renders the deploy-side `.env.local` from the root `config.yaml`
  - then deploys the control plane through Docker

## Migration Rules

- Treat `C:\Users\Public\nas_home\AI\GameEditor\BrowserService` as the read-only
  source workspace during this migration line.
- Do not delete, rewrite, or reorder files in the old workspace while
  restructuring this public repo.
- Perform all cleanup and path rewrites only in this target repository.

## Release Contract

This repository follows the EasyAiMi release contract v1 for GitHub Actions, GHCR publication, R2 config distribution, encrypted import-code artifacts, and blank-host local deployment. See [docs/release-contract.md](docs/release-contract.md) for the exact contract and project-specific exceptions.
