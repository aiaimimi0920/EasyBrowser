# Admin Endpoints Skeleton

This file outlines the current admin API skeleton only.

## Planned endpoints

### `GET /admin/providers`

Purpose:

- inspect provider availability, health, and cooldown state

### `GET /admin/providers/health-summary`

Purpose:

- inspect provider-level health summaries, including recent runtime lifecycle
  signals and task success/failure rates

### `GET /admin/runtimes`

Purpose:

- inspect runtime pool inventory

### `POST /admin/runtimes/spawn/:providerId`

Purpose:

- spawn one runtime using the provider's real process implementation when available

### `POST /admin/runtimes/spawn-stub/:providerId`

Purpose:

- spawn one stub runtime process for a provider for local validation

### `GET /admin/stats/providers`

Purpose:

- inspect provider-level stats

### `GET /admin/stats/runtimes`

Purpose:

- inspect runtime-level stats

### `GET /admin/routes/history`

Purpose:

- inspect recent route decisions, including diagnostics and candidate scoring

### `GET /admin/routes/fallbacks`

Purpose:

- inspect recent fallback route decisions only

### `GET /admin/routes/rejections`

Purpose:

- inspect aggregated provider rejection reasons across recent task history

### `GET /admin/routes/insights`

Purpose:

- inspect route analytics grouped by provider and strategy profile

### `GET /admin/routes/insights/windows`

Purpose:

- inspect route analytics grouped by provider and strategy profile across fixed
  recent time windows

### `GET /admin/routes/windows`

Purpose:

- inspect route, fallback, rejection, and event statistics over fixed recent
  time windows

### `GET /admin/routes/summary`

Purpose:

- inspect a control-plane summary that combines recent events, recent fallbacks,
  top rejection reasons, provider selection counts, and strategy-profile usage

### `GET /admin/events/recent`

Purpose:

- inspect recent operational events such as route fallback, provider disable,
  cooldown transitions, abnormal runtime exits, and dispatch failures

### `POST /admin/providers/:providerId/cooldown/reset`

Purpose:

- clear or override cooldown state

### `POST /admin/providers/:providerId/disable`

Purpose:

- force-disable a provider

### `POST /admin/providers/:providerId/enable`

Purpose:

- re-enable a provider
