# EasyBrowser Provider Contract

Every provider adapter is expected to implement the same logical contract,
regardless of whether the provider is local or remote.

Current conceptual contract:

- identify provider capabilities
- validate whether the provider can satisfy a request
- start or bind to an isolated runtime when needed
- execute browser work through that runtime
- surface normalized success / failure output
- report health and runtime state to stats / cooling layers

## Canonical action layer

EasyBrowser now converges provider actions around a smaller canonical set and
keeps aliases for compatibility.

Examples:

- `open_resource`
- `list_resources`
- `get_resource`
- `close_resource`
- `open_page`
  - aliases still accepted:
    - `open_url`
    - `create_tab`
    - `new_page`
- `close_target`
  - aliases still accepted:
    - `close_page`
    - `close_tab`
- `activate_target`
  - aliases still accepted:
    - `activate_page`
    - `activate_tab`
- `request_release`
  - alias still accepted:
    - `close_session`

Generic resource actions are now the preferred cross-provider surface for
callers that want one shape across local page providers and remote session
providers:

- `resource_kind=page`
  - routes to local browser providers such as `chrome` and `camoufox`
- `resource_kind=session`
  - routes to `browserbase`

Strategy mode now also honors `target.strategy_profile`. Current canonical
profiles include:

- `balanced`
- `local-first`
- `remote-first`
- `latency-first`
- `stability-first`
- `cost-aware`
- `stealth-first`
- `chrome-first`
- `camoufox-first`
- `browserbase-first`

Aliases such as `default`, `stealth`, `chrome`, `camoufox`, and
`browserbase` are normalized onto the canonical profile names.

Strategy scoring now also considers `isolation.runtime_reuse` hints:

- `prefer_reuse`
- `require_reuse`
- `prefer_fresh`
- `require_fresh`

When tasks are inspected through the unified API, the route reason now carries
score-oriented routing diagnostics, including the chosen profile, whether a
fallback was used, the profile rank, the final score, and the runtime-reuse
hint that affected selection.

The selected route is now also returned as structured diagnostics, not only as
one summary string. Callers can inspect:

- `route.diagnostics`
  - selected-action and selected-provider score summary
  - includes a structured `breakdown` of where the score came from
- `route.candidates`
  - scored candidate rows for each considered provider, including rejection
    reasons when a provider was filtered out

## Normalized result shape

Provider runtimes may use provider-native operations internally, but task
results returned through EasyBrowser now converge into a normalized result view
that looks like:

- `action`
- `provider_id`
- `runtime_id`
- `resource_kind`
- `resource`
- `resources`
- `resource_id`
- `count`
- `metadata`
- `provider_response`

Where:

- `resource` is used for single objects such as one page or one session
- `resources` is used for list-style operations
- `provider_response` contains sanitized provider-native data
- `metadata` carries cross-provider summary data such as browser version,
  debug port, project id, region, and similar high-signal fields

Current provider set:

- `chrome`
- `camoufox`
- `browserbase`

The `browserbase` provider is treated as a remote-provider adapter inside this
repository, not as a top-level workspace repository.
