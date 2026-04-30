from __future__ import annotations

from typing import Any

from ...interfaces.context import BrowserContext
from ...interfaces.provider import BrowserProvider
from ...models.errors import ConnectionError
from ...models.options import LaunchOptions
from ..common.playwright_context import PlaywrightContext
from .api_client import BrowserbaseApiClient


class BrowserbaseProvider(BrowserProvider):
    """Provider adapter for Browserbase remote browser service.

    Creates a remote browser session via Browserbase API, then connects
    via Playwright CDP to the session's websocket endpoint.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        project_id: str | None = None,
        base_url: str = "https://api.browserbase.com",
    ) -> None:
        self._api = BrowserbaseApiClient(
            api_key=api_key,
            project_id=project_id,
            base_url=base_url,
        )
        self._playwright: Any | None = None
        self._browser: Any | None = None
        self._session_id: str | None = None

    @property
    def name(self) -> str:
        return "browserbase"

    async def launch(self, options: LaunchOptions | None = None) -> BrowserContext:
        opts = options or LaunchOptions()

        proxies: list[dict[str, Any]] | None = None
        if opts.proxy:
            proxies = [{
                "type": "custom",
                "server": opts.proxy.server,
                "username": opts.proxy.username,
                "password": opts.proxy.password,
            }]

        session = await self._api.create_session(
            project_id=opts.extra.get("project_id"),
            proxies=proxies,
            browser_settings=opts.extra.get("browser_settings"),
            keep_alive=opts.extra.get("keep_alive", False),
            region=opts.extra.get("region"),
        )

        self._session_id = session.get("id", "")
        connect_url = session.get("connectUrl", "")
        if not connect_url:
            raise ConnectionError(
                f"Browserbase session {self._session_id} did not return a connectUrl"
            )

        from playwright.async_api import async_playwright

        pw = await async_playwright().__aenter__()
        self._playwright = pw
        self._browser = await pw.chromium.connect_over_cdp(connect_url)

        contexts = self._browser.contexts
        if contexts:
            return PlaywrightContext(contexts[0])
        context = await self._browser.new_context()
        return PlaywrightContext(context)

    async def connect(self, endpoint: str, **kwargs: Any) -> BrowserContext:
        from playwright.async_api import async_playwright

        pw = await async_playwright().__aenter__()
        self._playwright = pw
        self._browser = await pw.chromium.connect_over_cdp(endpoint)
        contexts = self._browser.contexts
        if contexts:
            return PlaywrightContext(contexts[0])
        context = await self._browser.new_context()
        return PlaywrightContext(context)

    async def close(self) -> None:
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None

        if self._playwright:
            try:
                await self._playwright.__aexit__(None, None, None)
            except Exception:
                pass
            self._playwright = None

        if self._session_id:
            try:
                await self._api.close_session(self._session_id)
            except Exception:
                pass

        await self._api.close()

    async def is_connected(self) -> bool:
        return self._browser is not None and self._browser.is_connected()

    def capabilities(self) -> dict[str, Any]:
        return {
            "provider": "browserbase",
            "engine": "playwright-cdp",
            "context_isolation": True,
            "headless": True,
            "stealth": True,
            "proxy": True,
            "fingerprint": False,
            "remote_connect": True,
            "cloud": True,
        }
