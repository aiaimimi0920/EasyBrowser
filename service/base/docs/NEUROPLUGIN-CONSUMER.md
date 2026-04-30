# NeuroPlugin consumer entrypoint

EasyBrowser provides the official browser-orchestration consumer used by NeuroPlugin:

- `service/base/src/neuroplugin-consumer.ts`

This is the browser equivalent of EasyEmail and EasyProxy consumer entrypoints.

## What it exports

### Strategy helpers

- `normalizeBrowserProviderTypeKey(...)`
- `resolveBrowserStrategyMode(...)`

### Catalog-like descriptors

- `BROWSER_PROVIDER_GROUPS`
- `BROWSER_STRATEGIES`

### HTTP client

- `createFetchJsonHttpClient(...)`
- `HttpEasyBrowserClient`

## Official routes

The consumer targets the **official EasyBrowser browser contract**:

- `POST /v1/browser/sessions/acquire`
- `POST /v1/browser/sessions/{sessionId}/renew`
- `POST /v1/browser/sessions/{sessionId}/release`
- `POST /v1/browser/sessions/{sessionId}/steps`
- `POST /v1/browser/sessions/{sessionId}/flows/execute`
- `GET /v1/tasks/{taskId}`
- `GET /healthz`

Contract split:

- `/steps` is primitive-only
- `/flows/execute` is the medium-step flow entrypoint used by NeuroPlugin DST runners

Legacy compatibility routes are removed and must not be used.
