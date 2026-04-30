# IPC Transport Decision

## Current Recommendation

Primary transport:

- stdio

Message format:

- JSON envelopes

Recommended framing:

- one JSON message per line
- or JSON-RPC-like request/response shape when correlation is needed

## Why stdio first

- simplest parent-child ownership model
- no port allocation
- no extra local listener lifecycle
- easy capture of stderr separately for diagnostics
- easy restart and cleanup

## When localhost HTTP may still help

- developer debugging
- manual runtime probing
- isolated smoke testing of one child runtime

## Future escape hatch

If a provider later proves to need a different transport for technical reasons,
the IPC layer should adapt behind the same logical envelope and action model.
