# EasyBrowser API Surface

The active public browser API has three caller-facing lanes:

- `GET /healthz`
- `POST /v1/browser/sessions/*`
- `POST /v1/execute` / `GET /v1/tasks/*`

The browser session lane is now split cleanly by responsibility:

- `/v1/browser/sessions/{sessionId}/steps`
  - primitive-only browser actions
  - examples: `navigate`, `click`, `input_text`, `submit`, `wait_for`, `read_value`, `evaluate_script`
- `/v1/browser/sessions/{sessionId}/flows/execute`
  - medium-step browser flows
  - examples: `register_auth -> register_profile -> register_finalize`
  - EasyBrowser lowers each medium step into primitive actions before dispatching to the provider runtime

Admin and internal lanes remain:

- `api/admin/`
  - provider status, cooldown state, route history, runtime operations
- `api/internal/`
  - runtime registration, heartbeat, completion, and process coordination

Important boundary rule:

- Browser providers execute primitive actions only.
- Medium-step flow legality is validated by EasyBrowser Flow API, not by provider capability routing.
