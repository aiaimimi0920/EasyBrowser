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

## Notes

- fork users must define their own variables/secrets in their fork if they want
  hosted publish behavior there
- secret values do not transfer to forks
