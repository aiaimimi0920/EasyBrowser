# EasyBrowser Architecture

`EasyBrowser` is the unified API and runtime orchestrator for browser execution.

Current intended boundaries:

- `api/`
  - outward API surface
- `providers/`
  - backend-specific adapters
- `process-manager/`
  - child process lifecycle control
- `runtime-pool/`
  - isolated runtime instance allocation
- `ipc/`
  - communication boundary with child processes
- `strategy/`
  - backend selection logic
- `cooling/`
  - cooldown logic for unhealthy providers or runtimes
- `stats/`
  - error and health accounting
- `models/`
  - shared request / runtime / provider shapes
- `config/`
  - operator-facing configuration skeleton

This repository skeleton intentionally assumes that process isolation is a
first-class runtime concern rather than an implementation detail.
