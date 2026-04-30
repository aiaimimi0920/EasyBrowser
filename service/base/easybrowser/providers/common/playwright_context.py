from __future__ import annotations

from typing import Any, Callable

from ...interfaces.context import BrowserContext
from ...interfaces.page import BrowserPage
from .playwright_page import PlaywrightPage


class PlaywrightContext(BrowserContext):
    """BrowserContext adapter wrapping a Playwright async BrowserContext object.

    Shared by Camoufox, GeekezBrowser, and Browserbase providers.
    """

    def __init__(self, context: Any) -> None:
        self._context = context

    async def new_page(self) -> BrowserPage:
        page = await self._context.new_page()
        return PlaywrightPage(page)

    async def pages(self) -> list[BrowserPage]:
        return [PlaywrightPage(p) for p in self._context.pages]

    # --- Cookies & Storage ---

    async def cookies(self, urls: list[str] | None = None) -> list[dict[str, Any]]:
        if urls:
            return await self._context.cookies(urls)
        return await self._context.cookies()

    async def add_cookies(self, cookies: list[dict[str, Any]]) -> None:
        await self._context.add_cookies(cookies)

    async def clear_cookies(self) -> None:
        await self._context.clear_cookies()

    async def storage_state(self) -> dict[str, Any]:
        return await self._context.storage_state()

    # --- Initialization ---

    async def add_init_script(self, script: str) -> None:
        await self._context.add_init_script(script)

    # --- Timeout ---

    async def set_default_timeout(self, timeout_ms: int) -> None:
        self._context.set_default_timeout(timeout_ms)

    async def set_default_navigation_timeout(self, timeout_ms: int) -> None:
        self._context.set_default_navigation_timeout(timeout_ms)

    # --- Permissions ---

    async def grant_permissions(self, permissions: list[str], *, origin: str | None = None) -> None:
        kwargs: dict[str, Any] = {}
        if origin:
            kwargs["origin"] = origin
        await self._context.grant_permissions(permissions, **kwargs)

    async def clear_permissions(self) -> None:
        await self._context.clear_permissions()

    # --- Geolocation & Network ---

    async def set_geolocation(self, geolocation: dict[str, float] | None) -> None:
        await self._context.set_geolocation(geolocation)

    async def set_offline(self, offline: bool) -> None:
        await self._context.set_offline(offline)

    # --- Network interception ---

    async def route(self, url: str, handler: Callable[..., Any]) -> None:
        await self._context.route(url, handler)

    async def unroute(self, url: str) -> None:
        await self._context.unroute(url)

    # --- Lifecycle ---

    async def close(self) -> None:
        await self._context.close()
