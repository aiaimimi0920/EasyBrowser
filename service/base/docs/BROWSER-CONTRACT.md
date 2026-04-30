# EasyBrowser Official Browser Contract

This document defines the **only supported browser orchestration contract** after the rewrite.
Old BrowserService compatibility routes are **explicitly deprecated** and will be removed.

## Goals

- NeuroPlugin expresses **intent** only.
- EasyBrowser owns **routing, runtime ownership, and step execution**.
- Provider selection is **strategy-based by default**, with optional explicit pinning.

## Transport

All routes are HTTP JSON. The contract is **async-first** and returns a task handle.

### Common request envelope

```json
{
  "request_id": "optional string",
  "mode": "strategy | direct",
  "strategy_profile": "balanced | local-first | remote-first | stealth-first | chrome-first | camoufox-first | browserbase-first | latency-first | stability-first | cost-aware",
  "provider_hint": "chrome | camoufox | browserbase",
  "runtime_reuse": "prefer_reuse | require_reuse | prefer_fresh | require_fresh",
  "timeout_ms": 90000,
  "metadata": {
    "task_id": "optional caller id",
    "tags": ["optional", "labels"]
  },
  "payload": { }
}
```

### Common async response

```json
{
  "success": true,
  "code": "ok",
  "message": "accepted",
  "data": {
    "task_id": "task-000123",
    "state": "running",
    "route": {
      "mode": "strategy",
      "selected_provider": "chrome",
      "runtime_id": "rt-chrome-0001",
      "strategy_profile": "balanced"
    }
  }
}
```

### Task status

`GET /v1/tasks/{taskId}` returns the canonical task status already defined in `docs/API-FIELD-DRAFTS.md`,
including normalized results and route diagnostics.

## Browser session lifecycle

### Acquire session

`POST /v1/browser/sessions/acquire`

Payload:

```json
{
  "startup_url": "https://example.com/",
  "proxy": "optional proxy",
  "captcha_provider": "optional",
  "session_ttl_seconds": 900
}
```

Response is async; task result returns:

```json
{
  "resource_kind": "session",
  "resource": {
    "id": "sess-xyz",
    "provider_id": "chrome",
    "runtime_id": "rt-chrome-0001",
    "current_url": "https://example.com/"
  }
}
```

### Renew session

`POST /v1/browser/sessions/{sessionId}/renew`

Payload:

```json
{ "session_ttl_seconds": 900 }
```

### Release session

`POST /v1/browser/sessions/{sessionId}/release`

No body required. Result returns a session resource with updated state.

## Browser step execution

### Execute step on a session

`POST /v1/browser/sessions/{sessionId}/steps`

Payload:

```json
{
  "step_type": "navigate | click | input_text | submit | wait_for | read_value | evaluate_script",
  "target": { "selector": "optional" },
  "input": { "value": "optional" }
}
```

Result returns a normalized action payload (see `docs/API-FIELD-DRAFTS.md`).

High-level browser orchestration is **not** accepted on `/steps`.
Requests that send `register_*`, `repair_*`, or `*_full` as `step_type` are rejected with a deprecated/invalid-request error and must use the Flow API below instead.

## Browser flow execution

### Execute a medium-step flow on a session

`POST /v1/browser/sessions/{sessionId}/flows/execute`

Payload:

```json
{
  "request_id": "optional string",
  "flow_type": "register | repair",
  "timeout_ms": 420000,
  "metadata": {
    "task_id": "optional caller id"
  },
  "steps": [
    {
      "step_type": "register_auth | register_profile | register_finalize | repair_login | repair_finalize",
      "target": { "selector": "optional" },
      "input": { "value": "optional" },
      "timeout_ms": 60000,
      "metadata": {
        "id": "optional caller step id"
      }
    }
  ]
}
```

Flow execution is async and returns the normal task handle. `GET /v1/tasks/{taskId}` then returns:

- `medium_step_results`
- `primitive_trace`
- `artifacts`
- structured `error` when the flow fails

EasyBrowser owns medium-step lowering. Browser providers only execute primitive actions and do not receive `register_*`, `repair_*`, `register_full`, or `repair_full` as provider actions.

## Provider override rules

- `mode=strategy` is the default.
- `provider_hint` is allowed but optional.
- `mode=direct` is only valid when `provider_hint` is supplied.
- If a provider does not support the requested primitive action, the request is rejected with `unsupported_action`.

## Compatibility removal notice

The following legacy routes are **not part of the official contract** and are scheduled for removal:

- `/register`
- `/repair-browser`
- `/sessions/register`
- `/sessions/repair`
- `/sessions/step` (legacy pre-`v1/browser/...` shape)
- `/sessions/acquire` (legacy shape)
- `/sessions/release` (legacy shape)
- `/health` (legacy shape)

All browser orchestration must move to the official `v1/browser/*` surface.
