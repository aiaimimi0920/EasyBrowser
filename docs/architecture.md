# Architecture

## Goal

EasyBrowser is the public monorepo for browser orchestration in the Easy*
service family.

It replaces the older multi-repo BrowserService workspace entrypoint with one
contributor-facing repository while preserving internal module boundaries.

## Top-Level Areas

### `service/base`

The main EasyBrowser control plane.

Responsibilities:

- outward HTTP API
- runtime and task registry
- browser session orchestration
- provider strategy and cooldown logic
- child-process supervision
- operational telemetry

### `runtimes/chrome`

The self-owned Chrome runtime.

Responsibilities:

- local browser bootstrap
- stealth/profile/proxy logic
- runtime-local browser workflows

### `upstreams/camoufox`

The upstream-tracked Camoufox fork area.

### `upstreams/geekez-browser`

The upstream-tracked GeekezBrowser fork area.

This subtree intentionally keeps source code only. Heavy downloaded browsers,
install outputs, and local build directories are excluded from the public repo.

## Why There Are No Submodules

Submodules would reintroduce the contributor complexity the migration is trying
to remove:

- contributors would need to discover multiple repositories
- pull request targets would become ambiguous
- cross-cutting changes would be harder to review

This monorepo keeps public contribution in one place while preserving the
maintenance-topology distinction between self-owned runtime code and
upstream-tracked code.

## Runtime Model

EasyBrowser treats process isolation as a first-class runtime boundary.

The control plane may:

- launch local provider runtimes
- supervise multiple isolated runtime instances
- route browser work by strategy or direct targeting
- expose normalized attach contracts for upstream callers

Browserbase remains an internal provider adapter inside `service/base`, not a
top-level repository.
