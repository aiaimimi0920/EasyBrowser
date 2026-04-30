# IPC Message Types

Current recommended message families:

- `request`
  - parent asks child runtime to do work
- `response`
  - child replies to a parent request
- `event`
  - child emits lifecycle or completion event
- `heartbeat`
  - child emits health update
- `error`
  - child emits normalized failure outside ordinary response flow

## Candidate actions

Parent to child:

- `prepare_runtime`
- `execute_task`
- `drain_runtime`
- `shutdown_runtime`
- `collect_health`

Child to parent:

- `runtime_ready`
- `task_completed`
- `runtime_health`
- `runtime_fault`
- `runtime_stopped`
