# EasyBrowser Task and Runtime States

This file records the current state-model skeleton.

## Task States

A task is the caller-facing unit of work.

Current intended task states:

- `queued`
- `routing`
- `allocating`
- `starting_runtime`
- `running`
- `succeeded`
- `failed`
- `timed_out`
- `cancelled`

## Runtime States

A runtime is the isolated execution instance or process.

Current intended runtime states:

- `created`
- `starting`
- `ready`
- `leased`
- `busy`
- `draining`
- `cooled`
- `failed`
- `stopped`

## Why Keep Them Separate

Task state and runtime state should not be collapsed together.

Reasons:

- one runtime may execute many tasks over time
- one task may wait before a runtime is assigned
- one runtime may fail independently of the task queue
- cooling may apply to a runtime even when no current task exists
