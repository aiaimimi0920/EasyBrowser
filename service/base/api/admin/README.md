# admin API

Reserved for operator-facing endpoints.

Typical future concerns:

- inspect provider availability
- inspect runtime-pool occupancy
- inspect cooldown state
- inspect error statistics
- force provider disable / enable

Current draft files:

- `ENDPOINTS.md`
- `provider-health-summary.response.example.yaml`
- `providers.response.example.yaml`
- `runtimes.response.example.yaml`
- `provider-stats.response.example.yaml`
- `runtime-stats.response.example.yaml`
- `route-history.response.example.yaml`
- `fallback-history.response.example.yaml`
- `route-rejections.response.example.yaml`
- `route-insights.response.example.yaml`
- `route-window-insights.response.example.yaml`
- `route-windows.response.example.yaml`
- `route-summary.response.example.yaml`
- `operational-events.response.example.yaml`

Current live admin routes also include:

- `GET /admin/providers/health-summary`
- `POST /admin/runtimes/spawn/{providerId}`
- `POST /admin/runtimes/spawn-stub/{providerId}`
- `GET /admin/routes/history`
- `GET /admin/routes/fallbacks`
- `GET /admin/routes/rejections`
- `GET /admin/routes/insights`
- `GET /admin/routes/insights/windows`
- `GET /admin/routes/windows`
- `GET /admin/routes/summary`
- `GET /admin/events/recent`
