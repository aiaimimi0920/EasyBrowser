# Internal Endpoints Skeleton

This file outlines the current internal API skeleton only.

## Planned internal coordination points

### runtime registration

- runtime announces readiness

### runtime heartbeat

- runtime updates health / liveness

### runtime completion event

- runtime reports task completion

### supervisor fault event

- parent process records child failure

## Important note

If the final implementation chooses non-HTTP IPC for some internal paths,
these logical endpoints may still survive as message topics or protocol frames
instead of HTTP routes.
