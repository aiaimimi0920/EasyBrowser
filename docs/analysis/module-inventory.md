# Module Inventory

## Summary Table

| Target module | Current source | Type | Approx source state | Complexity | Notes |
| --- | --- | --- | --- | --- | --- |
| `service/base` | `BrowserService\repos\EasyBrowser` | self-owned core service | about 259 files / about 309 MB in working copy | High | mixed source + compiled binaries + docker assets |
| `runtimes/chrome` | `BrowserService\repos\chrome` | self-owned runtime | about 117 files / about 1.3 MB | Medium | concentrated Python runtime and stealth helpers |
| `upstreams/camoufox` | `BrowserService\repos\camoufox` | upstream fork slot | placeholder only | Low | migration target exists before real import |
| `upstreams/geekez-browser` | `BrowserService\repos\GeekezBrowser` | upstream-tracked fork | about 14.5k files / about 1.2 GB working copy | High | includes `node_modules/` and build outputs that must be excluded |
| `deploy/service/base` | `BrowserService\deploy\EasyBrowser` | deploy assets | about 8 files / trivial size | Low | already separated cleanly from source |
| `docs` | `BrowserService\docs` and `repos\EasyBrowser\docs` | documentation | small but architecture-critical | Medium | split between workspace docs and repo-local API/contract docs |

## Detailed Inventory

### 1. `service/base`

Current source:

- `C:\Users\Public\nas_home\AI\GameEditor\BrowserService\repos\EasyBrowser`

Responsibility:

- outward EasyBrowser HTTP API
- runtime selection and lease control
- provider strategy and cooldown logic
- runtime spawn/supervision
- browser session APIs and medium-step flow execution
- internal Browserbase adapter handling

Important subareas:

- `cmd/easybrowser`
- `internal/app`
- `internal/httpapi`
- `internal/service`
- `internal/processmanager`
- `internal/browser`
- `providers/`
- `docker/`
- `docs/`
- `scripts/`

Public/API surface:

- `GET /healthz`
- `POST /v1/browser/sessions/*`
- `POST /v1/execute`
- `GET /v1/tasks/{taskId}`
- admin control-plane endpoints
- internal runtime lifecycle endpoints

Dependencies:

- depends on Chrome / Camoufox / Geekez / Browserbase provider semantics
- depends on deploy scripts and Dockerfile conventions
- depends on runtime path assumptions that currently point back into the old
  workspace

Migration note:

- must be copied first because it defines the public repository identity
- must be sanitized to remove compiled binaries and local runtime leftovers

### 2. `runtimes/chrome`

Current source:

- `C:\Users\Public\nas_home\AI\GameEditor\BrowserService\repos\chrome`

Responsibility:

- self-owned local Chrome runtime
- stealth/bootstrap behavior
- proxy/profile helpers
- browser-local flow helpers inherited from the legacy anonymous runtime line

Important subareas:

- `src/browser_runtime/runtime_entry.py`
- `driver_factory.py`
- `profile_manager.py`
- `proxy_extension.py`
- register/repair helper modules

Public/API surface:

- not a direct end-user API module
- exposed indirectly through EasyBrowser runtime spawning and attach contracts

Dependencies:

- EasyBrowser process manager spawn paths
- Python runtime and browser dependencies

Migration note:

- belongs under `runtimes/`, not `upstreams/`
- likely needs its own readme, smoke scripts, and possible future CI hooks

### 3. `upstreams/camoufox`

Current source:

- `C:\Users\Public\nas_home\AI\GameEditor\BrowserService\repos\camoufox`

Responsibility:

- reserved fork slot for upstream-tracked Camoufox customization

Current maturity:

- placeholder only

Dependencies:

- EasyBrowser provider/runtime integration
- future upstream sync workflow

Migration note:

- should still exist in the public monorepo even if currently light, because
  the directory communicates maintenance topology and future intent clearly

### 4. `upstreams/geekez-browser`

Current source:

- `C:\Users\Public\nas_home\AI\GameEditor\BrowserService\repos\GeekezBrowser`

Responsibility:

- upstream-tracked Electron stealth browser
- fingerprint isolation
- integrated proxy/network engine
- multi-account environment orchestration

Public/API surface:

- contributor-facing upstream application code
- consumed by EasyBrowser conceptually as a provider path

Dependencies:

- Node/Electron toolchain
- upstream project layout

Migration note:

- current working copy is oversized because it includes local install/build
  outputs
- public import must exclude `node_modules/`, `out/`, and other ignored paths

### 5. `deploy/service/base`

Current source:

- `C:\Users\Public\nas_home\AI\GameEditor\BrowserService\deploy\EasyBrowser`

Responsibility:

- Dockerfile for EasyBrowser service image
- start/probe/smoke scripts for operator flows

Current assets:

- `Dockerfile`
- `.env.example`
- `scripts/start-easybrowser.ps1`
- `scripts/probe-easybrowser.ps1`
- `scripts/smoke-open-page.ps1`

Migration note:

- this area is already structurally aligned with the target monorepo model
- should be copied with minimal transformation other than path rewrites

### 6. `docs`

Current source:

- workspace docs under `BrowserService\docs`
- service docs under `BrowserService\repos\EasyBrowser\docs`

Responsibility:

- workspace architecture explanation
- repository map
- process isolation and API contracts
- provider/runtime design notes

Migration note:

- docs should be split between:
  - root repo architecture/contributor docs
  - `service/base` local implementation docs if still useful

## Candidate Old-to-New Mapping

| Old path | New path |
| --- | --- |
| `BrowserService\repos\EasyBrowser` | `EasyBrowser\service\base` |
| `BrowserService\repos\chrome` | `EasyBrowser\runtimes\chrome` |
| `BrowserService\repos\camoufox` | `EasyBrowser\upstreams\camoufox` |
| `BrowserService\repos\GeekezBrowser` | `EasyBrowser\upstreams\geekez-browser` |
| `BrowserService\deploy\EasyBrowser` | `EasyBrowser\deploy\service\base` |
| `BrowserService\docs\*` | `EasyBrowser\docs\` |

## Highest-Risk Inventory Findings

- `service/base` is the main complexity center.
- `upstreams/geekez-browser` is the main sanitization center.
- `runtimes/chrome` is the main legacy-runtime compatibility center.
- `upstreams/camoufox` is structurally important even though it is currently
  light.
