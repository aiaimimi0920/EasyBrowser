# EasyBrowser Provider Methods

This file defines a **language-neutral method skeleton** for provider adapters.

It is not a final programming interface yet.

## Core Provider Methods

Every provider adapter should eventually implement these logical methods.

### `describeCapabilities()`

Purpose:

- return normalized provider capability information

Expected output:

- provider identity
- capability flags
- concurrency limits
- local / remote execution traits

### `validateRequest(request)`

Purpose:

- determine whether the provider can satisfy the normalized request

Expected output:

- supported / unsupported decision
- validation reason
- optional constraints or warnings

### `prepareRuntime(request, allocationContext)`

Purpose:

- bind to an existing runtime or prepare the provider side of a new runtime

Expected output:

- runtime preparation result
- runtime requirements
- spawn hints when a fresh runtime is needed

### `execute(request, runtimeContext)`

Purpose:

- perform browser work through the selected runtime

Expected output:

- normalized result payload
- normalized provider timing
- normalized provider error on failure

### `normalizeError(rawError, context)`

Purpose:

- convert provider-specific failure details into the shared error shape

Expected output:

- normalized error category
- retriable flag
- cooldown candidate flag
- raw details passthrough for operator inspection

### `collectHealth(runtimeContext)`

Purpose:

- return provider or runtime health information for stats and supervision layers

Expected output:

- health snapshot
- heartbeat info when available
- provider-specific degradation signals

## Optional Provider Methods

These are not guaranteed, but the structure should allow them later.

### `warmup(runtimeContext)`

- perform readiness checks before a runtime enters the available pool

### `drain(runtimeContext)`

- stop assigning new work while allowing active work to finish

### `shutdown(runtimeContext)`

- terminate or detach the runtime cleanly

### `recover(runtimeContext)`

- attempt limited recovery before marking the runtime failed

## Important Boundary

Providers should not own:

- global strategy routing
- global cooldown policy
- global runtime-pool ownership semantics

Providers do own:

- provider-specific validation
- provider-specific execution
- provider-specific normalization
