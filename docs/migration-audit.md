# Migration Audit

## Source To Target Mapping

| Source workspace path | Target monorepo path | Status |
| --- | --- | --- |
| `BrowserService\repos\EasyBrowser` | `service/base` | imported |
| `BrowserService\repos\chrome` | `runtimes/chrome` | imported |
| `BrowserService\repos\camoufox` | `upstreams/camoufox` | imported |
| `BrowserService\repos\GeekezBrowser` | `upstreams/geekez-browser` | imported with sanitization |
| `BrowserService\deploy\EasyBrowser` | `deploy/service/base` | imported |

## Intentional Exclusions

These exclusions were applied only in the target repo:

### `service/base`

- `.git/`
- compiled `.exe` and `.exe~` outputs
- `*.pyc`
- `__pycache__/`
- log files

### `runtimes/chrome`

- `.git/`
- `*.pyc`
- `__pycache__/`

### `upstreams/geekez-browser`

- `.git/`
- `node_modules/`
- `dist/`
- `release/`
- `userData/`
- `BrowserProfiles/`
- `_Trash_Bin/`
- `website/`
- `tools/`
- `out/`
- `resources/bin/`
- `resources/puppeteer/`
- `*.log`
- `*.exe`

### `deploy/service/base`

- probe log files

## Why The Geekez Exclusions Are Correct

The upstream `setup.js` flow already downloads runtime assets into ignored local
directories. Keeping those heavyweight payloads out of the public monorepo
improves clone size and contributor ergonomics without losing source fidelity.

## Residual Operational Path Audit

A scan of imported runtime code, deploy code, Dockerfiles, and root automation
after path rewrites found no remaining operational references to:

- legacy `repos/EasyBrowser` source-tree runtime paths
- old `/opt/browserservice/...` Docker paths
- source-workspace absolute paths inside service/deploy/runtime automation

## Target-Only Additions

The new public monorepo adds these target-only areas on purpose:

- root `docs/`
- root `scripts/`
- root `.github/workflows/`
- root `config.example.yaml`
- root progress and planning artifacts

These are migration outputs, not source omissions.

## Unexpected Omissions

No unexpected omissions were found in the imported mapping covered by this
public-repo migration pass. Differences between source and target are limited to
the intentional sanitization and public-repository additions documented above.

## Post-Migration Distribution Additions

The public monorepo now also includes target-only hosted distribution logic that
did not exist in the original source workspace:

- GitHub Secrets-driven config materialization overlays
- private R2 runtime-config upload scripts
- EasyBrowser import-code encode/encrypt/decrypt tooling
- optional local bootstrap JSON generation for R2-backed runtime retrieval
