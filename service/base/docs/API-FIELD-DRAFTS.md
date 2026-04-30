# EasyBrowser API Field Drafts

This file records field-level API drafts for the first outward and operator
surfaces.

These are still drafts, not final contracts.

## Public API

### `POST /v1/execute`

Purpose:

- submit one normalized execution request

Top-level request fields:

- `request_id`
  - optional caller-supplied correlation id
- `mode`
  - `strategy` or `direct`
  - `specified` is accepted as an alias of `direct`
- `target`
  - routing preferences and provider restrictions
  - `strategy_profile` is honored in `strategy` mode
  - currently supported canonical profiles:
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
  - `isolation.runtime_reuse` is now also used by strategy scoring
    - `prefer_reuse`
    - `require_reuse`
    - `prefer_fresh`
    - `require_fresh`
- `operation`
  - the work to perform
- `timeout`
  - total and startup timeout hints
- `retry`
  - retry hints
- `isolation`
  - separate-process and runtime-reuse requirements
- `metadata`
  - caller labels, tags, and audit hints

Top-level response fields:

- `success`
- `code`
- `message`
- `data.task_id`
- `data.state`
- `data.route.mode`
- `data.route.strategy_profile`
- `data.route.selected_provider`
- `data.route.runtime_id`
- `data.route.diagnostics`
- `trace.request_id`
- `trace.task_id`

### `GET /v1/tasks/:taskId`

Purpose:

- inspect the current normalized task view

Top-level response fields:

- `success`
- `code`
- `message`
- `data.task_id`
- `data.state`
- `data.mode`
- `data.route`
- `data.timing`
- `data.result`
- `data.error`
- `trace`

Route details now also surface:

- `strategy_profile`
- `fallback_used`
- `considered_providers`
- `rejected_providers`
- `strategy_reason`
  - now includes score-oriented details such as:
    - `profile`
    - `runtime_reuse`
    - `profile_rank`
    - `score`
- `diagnostics`
  - structured score data for the selected route
  - includes:
    - `action`
    - `action_class`
    - `resource_kind`
    - `runtime_reuse`
    - `profile`
    - `profile_rank`
    - `score`
    - `ready_runtimes`
    - `recent_failures`
    - `total_failures`
    - `breakdown`
      - `base_score`
      - `profile_bonus`
      - `reuse_bonus`
      - `ready_runtime_bonus`
      - `recent_failure_penalty`
      - `total_failure_penalty`
- `candidates`
  - structured provider-by-provider route diagnostics
  - each candidate may include:
    - `provider_id`
    - `eligible`
    - `selected`
    - `profile_rank`
    - `score`
    - `ready_runtimes`
    - `recent_failures`
    - `total_failures`
    - `rejection_reason`
    - `supports_action`
    - `supports_mode`
    - `provider_enabled`
    - `cooldown_active`
    - `breakdown`

Normalized `data.result` fields now converge around:

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

Notes:

- `provider_response` is sanitized before returning to callers
- local browser providers now prefer canonical action names such as
  `open_page`, even if older aliases were accepted on input
- generic resource actions are now supported:
  - `open_resource`
  - `list_resources`
  - `get_resource`
  - `close_resource`
- for generic resource actions in `strategy` mode, callers should include
  `payload.resource_kind`, currently:
  - `page`
  - `session`

### `POST /v1/tasks/:taskId/cancel`

Purpose:

- request task cancellation

Top-level request fields:

- `reason`
- `requested_by`

Top-level response fields:

- `success`
- `code`
- `message`
- `data.task_id`
- `data.cancel_state`
- `trace`

## Admin API

### `GET /admin/providers`

Purpose:

- inspect provider-level state

Top-level response fields:

- `success`
- `code`
- `message`
- `data.providers[]`

Each provider item should later expose:

- `provider_id`
- `kind`
- `enabled`
- `disabled_reason`
- `cooldown_active`
- `cooldown_until`
- `healthy`
- `failure_count`
- `last_error`
- `last_failure_at`
- `last_success_at`
- `capabilities`
- `limits`
- `stats_summary`

### `GET /admin/providers/health-summary`

Purpose:

- inspect provider-level health summaries and recent runtime lifecycle health
  signals

Typical response data:

- `providers[].provider_id`
- `providers[].enabled`
- `providers[].healthy`
- `providers[].cooldown_active`
- `providers[].failure_count`
- `providers[].last_error`
- `providers[].last_failure_at`
- `providers[].last_success_at`
- `providers[].total_task_succeeded_count`
- `providers[].total_task_failed_count`
- `providers[].total_task_cancelled_count`
- `providers[].total_spawn_started_count`
- `providers[].total_startup_failed_count`
- `providers[].total_ready_timeout_count`
- `providers[].total_heartbeat_missed_count`
- `providers[].total_heartbeat_restored_count`
- `providers[].total_health_degraded_count`
- `providers[].windows[].window`
- `providers[].windows[].since`
- `providers[].windows[].task_succeeded_count`
- `providers[].windows[].task_failed_count`
- `providers[].windows[].task_cancelled_count`
- `providers[].windows[].spawn_started_count`
- `providers[].windows[].startup_failed_count`
- `providers[].windows[].ready_timeout_count`
- `providers[].windows[].heartbeat_missed_count`
- `providers[].windows[].heartbeat_restored_count`
- `providers[].windows[].health_degraded_count`
- `providers[].windows[].success_rate`
- `providers[].windows[].failure_rate`

### `GET /admin/runtimes`

Purpose:

- inspect runtime-instance state

Top-level response fields:

- `success`
- `code`
- `message`
- `data.runtimes[]`

Each runtime item should later expose:

- `runtime_id`
- `provider_id`
- `state`
- `healthy`
- `pid`
- `current_task_id`
- `lease_id`
- `cooldown_active`
- `cooldown_until`
- `failure_count`
- `last_error`
- `last_failure_at`
- `last_success_at`
- `last_heartbeat_at`

### `GET /admin/stats/providers`

Purpose:

- inspect provider metrics

Typical response data:

- provider id
- total requests
- total successes
- total failures
- cooldown count
- recent failure window

### `GET /admin/stats/runtimes`

Purpose:

- inspect runtime metrics

Typical response data:

- runtime id
- provider id
- total leases
- restart count
- abnormal exit count
- recent failures

### `GET /admin/routes/history`

Purpose:

- inspect recent route decisions with diagnostics and candidate scores

Typical response data:

- task id
- request id
- selected provider
- runtime id
- strategy profile
- fallback used
- diagnostics
- candidates
- queued / started / finished timing

### `GET /admin/routes/fallbacks`

Purpose:

- inspect recent route decisions where fallback was used

Typical response data:

- same shape as route history, filtered to `fallback_used=true`

### `GET /admin/routes/rejections`

Purpose:

- inspect aggregated route rejection reasons

Typical response data:

- provider id
- rejection reason
- count

### `GET /admin/routes/insights`

Purpose:

- inspect route analytics grouped by provider and strategy profile

Typical response data:

- `providers[].provider_id`
- `providers[].selected_count`
- `providers[].fallback_selected_count`
- `providers[].succeeded_count`
- `providers[].failed_count`
- `providers[].rejection_counts`
- `providers[].event_counts`
- `providers[].last_selected_at`
- `profiles[].strategy_profile`
- `profiles[].total_routes`
- `profiles[].fallback_routes`
- `profiles[].succeeded_count`
- `profiles[].failed_count`
- `profiles[].provider_selections`

### `GET /admin/routes/insights/windows`

Purpose:

- inspect route analytics grouped by provider and strategy profile across fixed
  recent windows

Typical response data:

- `windows[].window`
- `windows[].since`
- `windows[].providers[].provider_id`
- `windows[].providers[].selected_count`
- `windows[].providers[].fallback_selected_count`
- `windows[].providers[].succeeded_count`
- `windows[].providers[].failed_count`
- `windows[].providers[].rejection_counts`
- `windows[].providers[].event_counts`
- `windows[].providers[].last_selected_at`
- `windows[].profiles[].strategy_profile`
- `windows[].profiles[].total_routes`
- `windows[].profiles[].fallback_routes`
- `windows[].profiles[].succeeded_count`
- `windows[].profiles[].failed_count`
- `windows[].profiles[].provider_selections`

### `GET /admin/routes/windows`

Purpose:

- inspect fixed-window route control statistics

Typical response data:

- `windows[].window`
- `windows[].since`
- `windows[].total_routes`
- `windows[].total_fallbacks`
- `windows[].total_failures`
- `windows[].provider_selections`
- `windows[].profile_usage`
- `windows[].rejections`
- `windows[].event_counts`

### `GET /admin/routes/summary`

Purpose:

- inspect one control-plane summary payload for route visibility

Typical response data:

- `totals.total_routes`
- `totals.total_fallbacks`
- `recent_events`
- `recent_fallbacks`
- `top_rejections`
- `provider_selections`
- `profile_usage`
- `provider_health`
- `recent_operational_events`

### `GET /admin/events/recent`

Purpose:

- inspect recent operational events across routing and reliability layers

Typical response data:

- `event_id`
- `kind`
- `severity`
- `provider_id`
- `runtime_id`
- `task_id`
- `request_id`
- `occurred_at`
- `message`
- `details`

Recent event kinds now include:

- `runtime_spawn_started`
- `runtime_registered`
- `runtime_ready`
- `runtime_ready_timeout`
- `runtime_startup_failed`
- `runtime_heartbeat_missed`
- `runtime_heartbeat_restored`
- `runtime_health_degraded`
- `runtime_reused`
- `runtime_shutdown`
- `route_selected`
- `route_fallback`
- `provider_disabled`
- `provider_enabled`
- `provider_cooled`
- `runtime_cooled`
- `runtime_abnormal_exit`
- `dispatch_failed`
- `task_succeeded`
- `task_failed`
- `task_cancelled`

## Internal API

### Runtime registration draft

Typical fields:

- `runtime_id`
- `provider_id`
- `pid`
- `state`
- `started_at`

### Runtime heartbeat draft

Typical fields:

- `runtime_id`
- `provider_id`
- `healthy`
- `timestamp`
- `signals`

### Runtime completion draft

Typical fields:

- `runtime_id`
- `task_id`
- `success`
- `result`
- `error`
- `finished_at`
