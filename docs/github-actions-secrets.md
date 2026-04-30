# GitHub Actions Secrets

EasyBrowser intentionally keeps hosted automation simple in the first public
release pass.

## Validate Workflow

`.github/workflows/validate.yml` does not require repository secrets.

It:

- checks out the repo
- installs Go, Node, and Python
- copies `config.example.yaml` to `config.yaml`
- runs `.\scripts\test-all.ps1`

## GHCR Publish Workflow

`.github/workflows/publish-service-base-ghcr.yml` uses the repository-scoped
`GITHUB_TOKEN` for package publishing.

Required permissions:

- `contents: read`
- `packages: write`

No extra GHCR password secret is required when publishing to the same
repository owner namespace.

## Optional Repository Variables

You may define these repository variables to customize publish behavior without
editing source:

| Variable name | Purpose | Default |
| --- | --- | --- |
| `EASYBROWSER_GHCR_IMAGE_NAME` | Override published image name | `easybrowser-service` |
| `EASYBROWSER_GHCR_NAMESPACE` | Override the owner/namespace segment | repository owner |
| `EASYBROWSER_GHCR_REGISTRY` | Override registry host | `ghcr.io` |

## Optional Repository Secrets

You may define these if you want hosted config materialization to diverge from
the default example config:

| Secret name | Purpose | Format |
| --- | --- | --- |
| `EASYBROWSER_SERVICE_LISTEN` | Override service listen address | Single line |
| `EASYBROWSER_CHROME_HEADLESS` | Override Chrome headless default | `true` / `false` |
| `EASYBROWSER_CHROME_USE_UNDETECTED_CHROMEDRIVER` | Override Chrome undetected-chromedriver mode | `true` / `false` |
| `EASYBROWSER_CHROME_BINARY_PATH` | Override Chrome binary path baked into rendered runtime env | Single line |
| `EASYBROWSER_CHROMEDRIVER_PATH` | Override chromedriver path baked into rendered runtime env | Single line |
| `EASYBROWSER_CHROME_PYTHON` | Override Chrome runtime Python path | Single line |
| `EASYBROWSER_CAMOUFOX_PYTHON` | Override Camoufox runtime Python path | Single line |
| `EASYBROWSER_CAMOUFOX_HEADLESS` | Override Camoufox headless mode | `true` / `false` |
| `EASYBROWSER_CAMOUFOX_OS` | Override Camoufox runtime OS hint | Single line |
| `EASYBROWSER_CAMOUFOX_READY_TIMEOUT_MS` | Override Camoufox ready timeout | Integer |
| `EASYBROWSER_GEEKEZ_PYTHON` | Override Geekez runtime Python path | Single line |
| `EASYBROWSER_GEEKEZ_READY_TIMEOUT_MS` | Override Geekez ready timeout | Integer |
| `EASYBROWSER_BROWSERBASE_API_KEY` | Browserbase API key for runtime env rendering | Single line |
| `EASYBROWSER_BROWSERBASE_PROJECT_ID` | Browserbase project id for runtime env rendering | Single line |
| `EASYBROWSER_IMPORT_CODE_SYNC_ENABLED` | Default import-code sync toggle | `true` / `false` |
| `EASYBROWSER_IMPORT_CODE_SYNC_INTERVAL_SECONDS` | Default import-code sync interval seconds | Integer |

## Notes

- fork users must define their own variables/secrets in their fork if they want
  hosted publish behavior there
- secret values do not transfer to forks

## Private R2 Runtime Config Distribution

`Publish Service Base GHCR` can also render the final `service/base` runtime
config and upload it to a private Cloudflare R2 bucket.

If the required `EASYBROWSER_R2_CONFIG_*` secrets are not configured, the
workflow keeps publishing the GHCR image and simply skips the R2 distribution
steps.

Required repository secrets for that path:

| Secret name | Purpose | Format |
| --- | --- | --- |
| `EASYBROWSER_R2_CONFIG_ACCOUNT_ID` | Cloudflare account id that owns the R2 bucket | Single line |
| `EASYBROWSER_R2_CONFIG_BUCKET` | Private R2 bucket name for EasyBrowser runtime config | Single line |
| `EASYBROWSER_R2_CONFIG_ENDPOINT` | Optional explicit R2 S3 endpoint | Single line |
| `EASYBROWSER_R2_CONFIG_CONFIG_OBJECT_KEY` | Object key for rendered `config.yaml` | Single line |
| `EASYBROWSER_R2_CONFIG_ENV_OBJECT_KEY` | Object key for rendered `runtime.env` | Single line |
| `EASYBROWSER_R2_CONFIG_MANIFEST_OBJECT_KEY` | Object key for the unified EasyBrowser distribution manifest | Single line |
| `EASYBROWSER_R2_CONFIG_UPLOAD_ACCESS_KEY_ID` | R2 upload access key id used by GitHub Actions | Single line |
| `EASYBROWSER_R2_CONFIG_UPLOAD_SECRET_ACCESS_KEY` | R2 upload secret access key used by GitHub Actions | Single line |

Optional repository secrets for owner-only import-code distribution:

| Secret name | Purpose | Format |
| --- | --- | --- |
| `EASYBROWSER_R2_CONFIG_READ_ACCESS_KEY_ID` | Client-side R2 read-only access key id | Single line |
| `EASYBROWSER_R2_CONFIG_READ_SECRET_ACCESS_KEY` | Client-side R2 read-only secret access key | Single line |
| `EASYBROWSER_IMPORT_CODE_OWNER_PUBLIC_KEY` | Owner-only import-code encryption public key | Single line |

## Encrypted Import Code Output

After a successful R2 upload, the publish workflow can:

- generate an EasyBrowser import code
- encrypt it with `EASYBROWSER_IMPORT_CODE_OWNER_PUBLIC_KEY`
- upload only the encrypted JSON as an Actions artifact

To recover the plain import code locally, keep the matching private key on the
trusted operator machine and run:

```powershell
.\scripts\decrypt-import-code.ps1 `
  -EncryptedFilePath .\easybrowser-import-code.encrypted.json `
  -PrivateKeyPath .\.runtime-keys\easybrowser_import_code_owner_private.txt `
  -ImportCodeOnly
```
