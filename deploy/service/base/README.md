# EasyBrowser Deploy Assets

This directory carries the operator-facing deploy helpers for the EasyBrowser
control plane under:

- `service/base`

## Runtime role

EasyBrowser is the single outward browser-resource API boundary in this
monorepo. It does **not** run captcha business logic for upstream services.
Instead it:

- allocates browser runtimes/resources
- returns a normalized `attach` contract
- lets upstream services attach to the leased browser/page/session and run
  their own logic
- releases the leased resource when the caller is done

## Actual local run path

### Build

```powershell
Set-Location service/base
go build -o .\easybrowser.exe .\cmd\easybrowser
```

### Start

Preferred helper:

```powershell
.\deploy\service\base\scripts\start-easybrowser.ps1
```

Direct start:

```powershell
$env:EASYBROWSER_LISTEN = "127.0.0.1:18080"
.\service\base\easybrowser.exe
```

The current local build reads:

- `EASYBROWSER_LISTEN`
  - default `127.0.0.1:18080`

## Probe helpers

- `scripts\probe-easybrowser.ps1`
  - checks `/healthz`, `/admin/providers`, `/admin/runtimes`
- `scripts\smoke-open-page.ps1`
  - submits `open_page`, polls `/v1/tasks/{taskId}`, prints the normalized
    `attach` contract, and closes the resource afterwards

## Unified attach contract

EasyBrowser currently returns these canonical fields in `data.result.attach`:

- `attach.scope`
  - `"page"` for a provider exposing an already-open page to attach to
  - `"browser"` for a provider exposing a browser/session where the caller
    should create its own page/context after attaching
- `attach.transport`
  - `"cdp"`
  - `"playwright_ws"`
- `attach.endpoint`
- `attach.browser_name`
- optional `attach.target_id`
- optional `attach.resource_id`
- optional `attach.page_url`

Current provider shapes:

- Chrome
  - `scope=page`, `transport=cdp`
- Camoufox
  - `scope=browser`, `transport=playwright_ws`

For browser-session callers, the same normalized `attach` contract should be
preserved in `/v1/browser/sessions/acquire` whenever the selected provider
supports outward attach semantics.

## Local Chrome env mapping

The local Python-backed Chrome runtime still reads legacy browser env names.
EasyBrowser maps the outward local env overrides onto that runtime when it
spawns a local Chrome child process:

- `EASYBROWSER_CHROME_HEADLESS` -> `HEADLESS` (`0` / `1`)
- `EASYBROWSER_CHROME_USE_UNDETECTED_CHROMEDRIVER` -> `USE_UNDETECTED_CHROMEDRIVER`
- `EASYBROWSER_CHROME_BINARY_PATH` -> `BROWSER_BINARY_PATH`
- `EASYBROWSER_CHROMEDRIVER_PATH` -> `CHROMEDRIVER_PATH`

## Current outward API usage

Typical browser-resource API usage:

- `POST /v1/execute`
- `GET /v1/tasks/{taskId}`
- `POST /v1/tasks/{taskId}/cancel`

Typical lease request:

- `operation.kind = "open_page"`
- `operation.payload.resource_kind = "page"`
- `operation.payload.url = "http://..."`

Typical release request:

- `operation.kind = "close_resource"`
- `operation.payload.resource_kind = "page"`
- `operation.payload.resource_id = "page-..."`

## Security note

The current local EasyBrowser build does not enforce a bearer token or API key
yet. Treat it as a localhost or private-network service boundary until hosted
auth is added.
