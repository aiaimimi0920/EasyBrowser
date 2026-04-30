# EasyBrowser Implementation Topology

Current recommended implementation split:

## Parent process

Suggested implementation language:

- Go

Responsibilities:

- expose public/admin APIs
- hold task registry
- hold runtime registry
- allocate leases
- run routing logic
- apply cooldown rules
- aggregate stats
- spawn and supervise child runtimes

## Child provider runtimes

### Chrome runtime

Suggested implementation language:

- Node.js / TypeScript

Reason:

- strong browser automation and script ecosystem

### Camoufox runtime

Suggested implementation language:

- Python

Reason:

- aligns with upstream-preferred usage style

### Browserbase runtime

Suggested implementation language:

- Node.js / TypeScript

Reason:

- API-centric integration and session-oriented workflows fit well here

## Communication rule

The parent should talk to child runtimes through one normalized IPC contract,
even if the child languages differ.

That keeps the parent-side logic stable while allowing provider-specific
implementations underneath.
