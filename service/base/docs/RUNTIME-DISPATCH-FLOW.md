# EasyBrowser Runtime Dispatch Flow

This file records the current dispatch and allocation skeleton.

## High-Level Flow

1. caller submits normalized execution request
2. API layer validates envelope shape
3. route mode is resolved:
   - direct
   - strategy
4. strategy layer selects a provider when needed
5. cooling layer rejects cooled providers or runtimes
6. allocator chooses one of:
   - reuse ready runtime
   - spawn fresh runtime
   - fail if no eligible route exists
7. lease is created for the chosen runtime
8. provider executes the task
9. stats are updated
10. lease is released
11. runtime returns to:
    - ready
    - draining
    - cooled
    - failed

## Direct Mode Skeleton

Direct mode path:

1. verify explicit provider target exists
2. verify provider is enabled
3. verify provider is not globally cooled unless operator override exists
4. allocate eligible runtime for that provider
5. execute task

## Strategy Mode Skeleton

Strategy mode path:

1. collect candidate providers
2. filter by request capability requirements
3. filter by provider enabled state
4. filter by cooldown state
5. rank remaining providers
6. try allocation in ranked order
7. fall back if first route fails before execution begins

## Allocation Outcomes

Allocator should normalize one of these outcomes:

- reused runtime
- fresh runtime spawned
- allocation blocked by cooldown
- allocation blocked by capacity
- allocation failed due to startup failure
- allocation failed due to no supported provider
