# Configuration

## Root Config Model

EasyBrowser uses one root operator config:

- `config.example.yaml`
- local ignored override: `config.yaml`

The root config is the contributor/operator entrypoint for local scripts and
hosted workflow materialization.

## Current Sections

### `serviceBase.runtime`

Current fields:

- `listen`

Purpose:

- control-plane listen address used by local scripts and future hosted runtime
  configuration

### `chromeRuntime`

Current fields:

- `headless`
- `useUndetectedChromedriver`
- `binaryPath`
- `chromedriverPath`
- `pythonPath`

Purpose:

- local Chrome runtime defaults

### `camoufoxRuntime`

Current fields:

- `pythonPath`
- `headless`
- `os`
- `readyTimeoutMs`

### `geekezRuntime`

Current fields:

- `pythonPath`
- `readyTimeoutMs`

### `browserbase`

Current fields:

- `apiKey`
- `projectId`

Purpose:

- runtime-side Browserbase credentials and project targeting

### `publishing.ghcr`

Current fields:

- `registry`
- `namespace`
- `imageName`

Purpose:

- default image naming for GHCR-related tooling

### `publishing.importCode`

Current fields:

- `syncEnabled`
- `syncIntervalSeconds`

Purpose:

- default import-code bootstrap behavior for R2-backed distribution

## Hosted Materialization

GitHub Actions can render `config.yaml` from `config.example.yaml` using:

```powershell
python .\scripts\materialize-action-config.py --base-config config.example.yaml --output config.yaml
```

The current materialization flow supports these env-driven overlays:

- `EASYBROWSER_SERVICE_LISTEN`
- `EASYBROWSER_CHROME_HEADLESS`
- `EASYBROWSER_CHROME_USE_UNDETECTED_CHROMEDRIVER`
- `EASYBROWSER_CHROME_BINARY_PATH`
- `EASYBROWSER_CHROMEDRIVER_PATH`
- `EASYBROWSER_CHROME_PYTHON`
- `EASYBROWSER_CAMOUFOX_PYTHON`
- `EASYBROWSER_CAMOUFOX_HEADLESS`
- `EASYBROWSER_CAMOUFOX_OS`
- `EASYBROWSER_CAMOUFOX_READY_TIMEOUT_MS`
- `EASYBROWSER_GEEKEZ_PYTHON`
- `EASYBROWSER_GEEKEZ_READY_TIMEOUT_MS`
- `EASYBROWSER_BROWSERBASE_API_KEY`
- `EASYBROWSER_BROWSERBASE_PROJECT_ID`
- `EASYBROWSER_GHCR_IMAGE_NAME`
- `EASYBROWSER_GHCR_NAMESPACE`
- `EASYBROWSER_GHCR_REGISTRY`
- `EASYBROWSER_IMPORT_CODE_SYNC_ENABLED`
- `EASYBROWSER_IMPORT_CODE_SYNC_INTERVAL_SECONDS`

## Local Safety Rules

- do not commit `config.yaml`
- keep secrets and machine-specific values out of source
- use `config.example.yaml` as the shared baseline only
