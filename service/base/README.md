# EasyBrowser Service Base

`service/base` is the EasyBrowser control plane inside the public monorepo.

It owns the outward HTTP API, provider strategy and cooldown logic, runtime
registration, task tracking, and local child-process supervision.

## Module Position In The Monorepo

```text
EasyBrowser/
├─ service/
│  └─ base/              <- this module
├─ runtimes/
│  └─ chrome/
├─ upstreams/
│  ├─ camoufox/
│  └─ geekez-browser/
├─ deploy/
│  └─ service/
│     └─ base/
├─ docs/
└─ scripts/
```

### Runtime boundary

- `runtimes/chrome`
  - self-owned Chrome runtime code copied from the legacy workspace
- `service/base/providers/camoufox`
  - current Camoufox runtime adapter used by the control plane
- `service/base/providers/geekez`
  - current Geekez runtime adapter used by the control plane
- `service/base/providers/browserbase`
  - internal Browserbase adapter

## Current Capability Direction

- strategy mode
- direct mode
- error cooling
- error statistics
- child process launch / supervision
- multi-process runtime isolation
- browser session acquire / renew / release / step / flow APIs

The core runtime assumption is unchanged after migration: process isolation is a
first-class reliability boundary rather than an implementation detail.

## Current Working Scaffold

The imported scaffold currently includes:

- Go entrypoint under `cmd/easybrowser/`
- in-memory task / provider / runtime service layer
- public / admin / internal HTTP endpoints
- stdio JSON envelope model
- provider runtime spawn/supervision logic
- browser session execution flow support
- smoke scripts under `scripts/`

## Build And Test

```powershell
Set-Location service/base
go test ./...
go build -o .\easybrowser.exe .\cmd\easybrowser
```

Operator-facing deploy helpers live under `deploy/service/base/`.

## Browser Resource Boundary

EasyBrowser is primarily a browser resource allocator and orchestration layer.
Upstream callers can request attachable browser resources, receive runtime and
attach metadata, run their own business logic, and release the resource when
finished.

Current attach contract examples:

- Chrome page lease:
  - `attach.scope = "page"`
  - `attach.transport = "cdp"`
  - `attach.endpoint = "http://127.0.0.1:<debug_port>"`
  - `attach.target_id = "<page-target-id>"`
- Camoufox browser/session lease:
  - `attach.scope = "browser"`
  - `attach.transport = "playwright_ws"`
  - `attach.endpoint = "ws://127.0.0.1:<port>/<token>"`
