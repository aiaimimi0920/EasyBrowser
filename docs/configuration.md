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

Purpose:

- local Chrome runtime defaults

### `publishing.ghcr`

Current fields:

- `imageName`

Purpose:

- default image naming for GHCR-related tooling

## Hosted Materialization

GitHub Actions can render `config.yaml` from `config.example.yaml` using:

```powershell
python .\scripts\materialize-action-config.py --base-config config.example.yaml --output config.yaml
```

The current materialization flow supports these env-driven overlays:

- `EASYBROWSER_SERVICE_LISTEN`
- `EASYBROWSER_CHROME_HEADLESS`
- `EASYBROWSER_GHCR_IMAGE_NAME`
- `EASYBROWSER_GHCR_NAMESPACE`
- `EASYBROWSER_GHCR_REGISTRY`

## Local Safety Rules

- do not commit `config.yaml`
- keep secrets and machine-specific values out of source
- use `config.example.yaml` as the shared baseline only
