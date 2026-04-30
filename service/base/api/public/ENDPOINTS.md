# Public Endpoints Skeleton

This file outlines the current public API skeleton only.

## Planned endpoints

### `POST /v1/execute`

Purpose:

- submit one browser execution request

Modes:

- `strategy`
- `direct`

Typical outward usage is to request browser resources or sessions, for example:

- `open_page`
- `open_resource`
- `list_resources`
- `get_resource`
- `close_resource`
- `create_session`
- `get_session`
- `request_release`

Attach metadata returned from these requests can then be consumed by upstream
services that own their own browser business logic.

Current normalized attach contract fields:

- `attach.scope`
  - `"page"` when the returned resource is an already-open page to attach to
  - `"browser"` when the caller should attach to the browser/session and create
    its own page/context
- `attach.transport`
  - `"cdp"` for Chrome-style CDP attachment
  - `"playwright_ws"` for Playwright websocket attachment
- `attach.endpoint`
- `attach.browser_name`
- optional `attach.target_id`
- optional `attach.resource_id`
- optional `attach.page_url`

### `GET /v1/tasks/:taskId`

Purpose:

- fetch normalized task status

### `POST /v1/tasks/:taskId/cancel`

Purpose:

- request task cancellation

## Public API design rules

- provider-specific details should remain optional metadata
- main payload should be normalized
- direct mode should require explicit provider target
- strategy mode should avoid leaking internal routing complexity by default
