# Quickstart

## Prerequisites

- Go `1.26+`
- Python `3.12+`
- Node.js `20.x`
- PowerShell

Optional for local runtime validation:

- Chrome/Chromium runtime dependencies for `runtimes/chrome`
- Python packages needed by the Chrome runtime
- Docker for image builds

## Initialize Local Config

```powershell
.\scripts\init-config.ps1
```

This creates a local `config.yaml` from `config.example.yaml` when one does not
already exist.

## Validate The Repository

```powershell
.\scripts\test-all.ps1
```

Current validation covers:

- `service/base` Go tests
- local service startup via deploy helper
- `/healthz` smoke probe

## Run The Control Plane

```powershell
.\scripts\start-service-base.ps1
```

Probe it with:

```powershell
.\scripts\probe-service-base.ps1
```

## Build The Service Image

```powershell
.\scripts\compile-service-base-image.ps1
```

## Chrome Runtime Notes

The control plane now resolves Chrome runtime code from:

- `runtimes/chrome/src/browser_runtime/runtime_entry.py`

## Geekez Upstream Notes

The public repo excludes heavy downloaded payloads such as bundled Chromium and
runtime binary blobs.

When you need those locally, install the upstream subtree from source:

```powershell
Set-Location upstreams/geekez-browser
npm install
```

The upstream `setup.js` flow downloads the required runtime assets into the
ignored local directories.
