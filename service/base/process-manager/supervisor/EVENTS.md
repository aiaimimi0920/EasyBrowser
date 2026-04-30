# Supervisor Events Skeleton

The supervisor layer should later normalize child-process events into a shared
event model.

Typical events:

- child_started
- child_ready
- child_exited
- child_crashed
- heartbeat_missed
- restart_scheduled
- restart_exhausted
- runtime_quarantined

These events should be consumable by:

- stats
- cooling
- allocator
- admin inspection APIs
