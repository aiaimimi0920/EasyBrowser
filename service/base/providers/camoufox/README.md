# camoufox provider

Local Camoufox runtime lives at:

- `C:\Users\Public\nas_home\AI\GameEditor\BrowserService\repos\EasyBrowser\providers\camoufox\runtime.py`

It launches a local Camoufox browser through Python and exposes a small set of provider actions through EasyBrowser's stdio runtime protocol.

## Local prerequisites

- Python available on PATH, or set `EASYBROWSER_CAMOUFOX_PYTHON`
- `camoufox` package installed
- Camoufox browser assets fetched locally

Typical setup commands:

- `python -m pip install camoufox`
- `python -m camoufox fetch`

## Optional environment variables

- `EASYBROWSER_CAMOUFOX_PYTHON`
- `EASYBROWSER_CAMOUFOX_HEADLESS`
- `EASYBROWSER_CAMOUFOX_OS`
- `EASYBROWSER_CAMOUFOX_READY_TIMEOUT_MS`
- `EASYBROWSER_CAMOUFOX_WS_TIMEOUT_MS`
- `EASYBROWSER_CAMOUFOX_CONNECT_TIMEOUT_MS`
- `EASYBROWSER_CAMOUFOX_GOTO_TIMEOUT_MS`

## Startup reliability notes

- EasyBrowser now gives the Camoufox child runtime a longer default ready timeout
  than other providers.
- The Camoufox runtime now emits startup-stage diagnostics to stderr, including
  the current stage and elapsed time.
- If startup still times out, the parent process will include recent Camoufox
  stderr lines in the surfaced error to improve cooldown / failure attribution
  debugging.

## Supported actions

- `get_version`
- `health`
- `list_pages`
- `list_targets`
- `open_page`
- `create_tab`
- `new_page`
- `activate_target`
- `close_target`

Aliases such as `open_url` still work, but `open_page` is now the preferred canonical action name.
