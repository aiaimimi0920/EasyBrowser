# scripts

Root operator scripts belong here.

Current entrypoints:

- `init-config.ps1`
- `test-all.ps1`
- `test-service-base-instance.ps1`
- `start-service-base.ps1`
- `probe-service-base.ps1`
- `smoke-open-page.ps1`
- `compile-service-base-image.ps1`
- `render-derived-configs.py`
- `render-derived-configs.ps1`
- `upload-service-base-r2-config.py`
- `upload-service-base-r2-config.ps1`
- `easybrowser-import-code.py`
- `generate-import-code-keypair.ps1`
- `decrypt-import-code.ps1`
- `write-service-base-r2-bootstrap.ps1`
- `materialize-action-config.py`
- `validate-release-tag.py`

The public monorepo prefers a small set of repository-root entrypoints for
build, validation, image publish preparation, deployment rendering, and smoke
checks, instead of forcing contributors to discover per-module commands
manually.
