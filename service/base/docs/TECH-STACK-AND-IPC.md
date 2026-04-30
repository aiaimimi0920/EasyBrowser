# EasyBrowser Tech Stack and IPC Recommendation

This document records the **current recommended default**, not a frozen final
decision.

## Recommended Topology

### Parent / Orchestrator: Go

Recommended role:

- outward API server
- provider routing
- runtime-pool allocation
- child process supervision
- cooldown and stats aggregation

Why Go is the current recommendation:

- strong fit for long-running service processes
- simple process spawning and lifecycle control
- low overhead for many concurrent tasks
- easy deployment as one static service binary
- good fit for supervisor-style orchestration

## Provider Runtime Recommendation

### Chrome provider child runtime: Node.js / TypeScript

Recommended because:

- Chrome automation ecosystem is strongest in Playwright / CDP tooling
- JavaScript ecosystem is typically the easiest place to integrate browser-side
  scripts and automation glue

### Camoufox provider child runtime: Python

Recommended because:

- Camoufox upstream strongly centers its Python interface
- keeping Camoufox close to its preferred upstream usage reduces integration
  friction

### Browserbase provider child runtime: Node.js / TypeScript

Recommended because:

- Browserbase is fundamentally an API / remote-session provider
- Browserbase documentation and examples are well aligned with modern JS/TS
  usage patterns
- keeping Browserbase as a provider child runtime still preserves the same
  process-isolation model used by other providers

## Recommended IPC

### Primary recommendation: stdio + JSON messages

Recommended default:

- one parent process
- one child runtime process
- bidirectional communication over stdio
- newline-delimited JSON or JSON-RPC style envelopes

Why this is the current recommendation:

- no port allocation needed
- no localhost port conflicts
- parent owns the child lifecycle directly
- easy to attribute logs, exit codes, and heartbeats to one child
- very good fit for process isolation
- cross-language friendly

## Secondary / Optional debugging transport

### localhost HTTP

Recommended only as a secondary debugging or development convenience, not as
the primary production IPC.

Useful for:

- manual local debugging
- runtime introspection during development
- isolated smoke tests against one child runtime

Not recommended as the default internal transport because:

- every child needs its own port management
- increases runtime coordination complexity
- adds another failure class around port binding and cleanup

## Current Non-Recommendations

### Named pipes as the primary default

Not recommended as the first default because:

- cross-platform ergonomics are less uniform
- debugging is usually less convenient than stdio

### gRPC as the primary default

Not recommended as the first default because:

- current contracts are still evolving rapidly
- schema and toolchain overhead is high for the current planning stage

### In-process provider execution as the primary default

Not recommended because the current architecture explicitly values:

- message isolation
- fault containment
- per-provider runtime independence

## Current Recommendation Summary

Recommended default stack:

- parent `EasyBrowser`: Go
- Chrome child runtime: Node.js / TypeScript
- Camoufox child runtime: Python
- Browserbase child runtime: Node.js / TypeScript
- parent/child IPC: stdio + JSON envelopes

This is the current recommendation because it best matches the current goals:

- unified outward API
- multi-process isolation
- provider-specific ecosystem compatibility
- higher availability through process separation
