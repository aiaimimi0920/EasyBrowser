# Provider Boundary — EasyBrowser <-> chrome runtime

This document defines the initial execution boundary between EasyBrowser and the migrated anonymous Chrome runtime.

## Execution model

- EasyBrowser spawns a **Python runtime process** from `repos/chrome/src/chrome_runtime/runtime_entry.py`.
- Communication uses stdio JSON envelopes consistent with existing EasyBrowser providers.
- The runtime owns the Selenium/undetected-chromedriver lifecycle and returns normalized execution results.

## Actions (initial)

The boundary supports the following actions initially:

- `acquire_session`
- `renew_session`
- `release_session`
- `step.navigate`
- `step.click`
- `step.input_text`
- `step.submit`
- `step.wait_for`
- `step.read_value`

## Payload shape

```json
{
  "action": "acquire_session",
  "payload": {
    "proxy": "optional",
    "browser_backend": "custom",
    "captcha_provider": "optional",
    "startup_url": "https://example.com/",
    "ttl_seconds": 900
  }
}
```

Step payload example:

```json
{
  "action": "step.navigate",
  "payload": {
    "session_id": "browser-session-abc",
    "target": { "url": "https://example.com/" }
  }
}
```

## Responses

The runtime returns:

```json
{
  "success": true,
  "result": {
    "resource_kind": "session",
    "resource": { "id": "browser-session-abc", "current_url": "https://example.com/" }
  }
}
```

## Migration note

This boundary is intentionally minimal. It preserves the legacy runtime behavior while enabling EasyBrowser to own
session lifecycle and step orchestration. The boundary will be refined in Phase 3 when the official EasyBrowser
browser API replaces the legacy compatibility layer.
