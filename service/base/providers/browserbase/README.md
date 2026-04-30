# browserbase provider

Browserbase remote-provider adapter lives inside:

- `C:\Users\Public\nas_home\AI\GameEditor\BrowserService\repos\EasyBrowser\providers\browserbase\runtime.js`

This provider is intentionally embedded inside `EasyBrowser`, not a top-level repository.

## Required environment variables

- `BROWSERBASE_API_KEY`

## Optional environment variables

- `BROWSERBASE_PROJECT_ID`
- `EASYBROWSER_BROWSERBASE_BASE_URL`  
  defaults to `https://api.browserbase.com`

## Supported action payloads

The child runtime accepts `operation.payload.action` values such as:

- `create_session`
- `list_sessions`
- `get_session`
- `update_session`
- `request_release`
- `close_session`
- `api_request`
- `health`

The generic `api_request` path is useful when Browserbase adds new endpoints and EasyBrowser has not yet wrapped them with a named action.

`close_session` is accepted as a friendlier alias for `request_release` and is normalized into the same provider operation.
