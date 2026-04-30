# Provider Method Skeleton

This directory is reserved for shared provider abstractions.

Current logical provider contract:

- `describeCapabilities`
- `validateRequest`
- `prepareRuntime`
- `execute`
- `normalizeError`
- `collectHealth`

Shared helpers in this directory should exist only when the behavior is truly
common across providers.
