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

The control plane is also the executor manager:

- tasks first enter the `service/base` routing and planning layer
- the process manager owns provider runtimes as child executors
- a small warm set of runtimes may stay alive even when idle
- additional runtimes are spawned on demand when task pressure arrives
- surplus idle runtimes are reaped after the configured idle timeout
