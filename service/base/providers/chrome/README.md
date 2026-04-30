# chrome provider

Local Chrome runtime lives at:

- `C:\Users\Public\nas_home\AI\GameEditor\BrowserService\repos\EasyBrowser\providers\chrome\runtime.js`

It launches a local Chrome-family browser with a dedicated profile and remote-debugging port, then exposes a small set of provider actions through EasyBrowser's stdio runtime protocol.

## Optional environment variables

- `EASYBROWSER_CHROME_PATH`
  - explicit browser executable path
- `EASYBROWSER_CHROME_HEADLESS`
  - defaults to `true`

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
