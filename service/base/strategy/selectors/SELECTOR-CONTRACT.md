# Selector Contract Skeleton

Selectors are responsible for ranking candidate providers and runtimes.

Typical selector inputs:

- request requirements
- provider capabilities
- provider health
- provider cooldown state
- runtime availability
- operator preference

Typical selector outputs:

- ranked provider list
- ranked runtime list
- route-decision reason string or metadata

Selectors should produce normalized decision metadata so task-status responses
can later explain why a route was chosen.
