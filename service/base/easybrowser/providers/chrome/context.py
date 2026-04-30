from __future__ import annotations

import asyncio
from typing import Any, Callable

from ...interfaces.context import BrowserContext
from ...interfaces.page import BrowserPage
from .page import ChromePage


class ChromeContext(BrowserContext):
    """BrowserContext adapter for Selenium WebDriver.

    Selenium has no true context isolation. This wraps the entire driver session
    as a single context. new_page() opens a new tab.
    """

    def __init__(self, driver: Any) -> None:
        self._driver = driver
        self._pages: list[ChromePage] = []
        self._init_scripts: list[str] = []
        self._closed = False

        handle = self._driver.current_window_handle
        page = ChromePage(self._driver, window_handle=handle)
        self._pages.append(page)

    async def new_page(self) -> BrowserPage:
        def _new() -> ChromePage:
            self._driver.execute_script("window.open('about:blank')")
            handles = list(self._driver.window_handles)
            new_handle = handles[-1]
            self._driver.switch_to.window(new_handle)
            for script in self._init_scripts:
                self._driver.execute_script(script)
            page = ChromePage(self._driver, window_handle=new_handle)
            self._pages.append(page)
            return page
        return await asyncio.to_thread(_new)

    async def pages(self) -> list[BrowserPage]:
        return list(self._pages)

    async def cookies(self, urls: list[str] | None = None) -> list[dict[str, Any]]:
        def _cookies() -> list[dict[str, Any]]:
            return self._driver.get_cookies()
        return await asyncio.to_thread(_cookies)

    async def add_cookies(self, cookies: list[dict[str, Any]]) -> None:
        def _add() -> None:
            for cookie in cookies:
                self._driver.add_cookie(cookie)
        await asyncio.to_thread(_add)

    async def clear_cookies(self) -> None:
        await asyncio.to_thread(self._driver.delete_all_cookies)

    async def storage_state(self) -> dict[str, Any]:
        def _state() -> dict[str, Any]:
            cookies = self._driver.get_cookies()
            local_storage: dict[str, str] = {}
            try:
                keys_script = "return Object.keys(localStorage);"
                keys = self._driver.execute_script(keys_script) or []
                for key in keys:
                    val = self._driver.execute_script(f"return localStorage.getItem({key!r});")
                    if val is not None:
                        local_storage[key] = str(val)
            except Exception:
                pass
            return {"cookies": cookies, "localStorage": local_storage}
        return await asyncio.to_thread(_state)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True

        def _close() -> None:
            try:
                self._driver.quit()
            except Exception:
                pass
        await asyncio.to_thread(_close)

    async def add_init_script(self, script: str) -> None:
        self._init_scripts.append(script)
        try:
            await asyncio.to_thread(
                lambda: self._driver.execute_cdp_cmd(
                    "Page.addScriptToEvaluateOnNewDocument", {"source": script}
                )
            )
        except Exception:
            pass

    async def set_default_timeout(self, timeout_ms: int) -> None:
        def _set() -> None:
            self._driver.implicitly_wait(timeout_ms / 1000.0)
        await asyncio.to_thread(_set)

    async def set_default_navigation_timeout(self, timeout_ms: int) -> None:
        def _set() -> None:
            self._driver.set_page_load_timeout(timeout_ms / 1000.0)
        await asyncio.to_thread(_set)

    async def grant_permissions(self, permissions: list[str], *, origin: str | None = None) -> None:
        # Selenium has no built-in permission API; use CDP if available.
        try:
            await asyncio.to_thread(
                lambda: self._driver.execute_cdp_cmd(
                    "Browser.grantPermissions",
                    {"permissions": permissions, **({"origin": origin} if origin else {})},
                )
            )
        except Exception:
            pass

    async def clear_permissions(self) -> None:
        try:
            await asyncio.to_thread(
                lambda: self._driver.execute_cdp_cmd("Browser.resetPermissions", {})
            )
        except Exception:
            pass

    async def set_geolocation(self, geolocation: dict[str, float] | None) -> None:
        def _set() -> None:
            try:
                if geolocation:
                    self._driver.execute_cdp_cmd("Emulation.setGeolocationOverride", {
                        "latitude": geolocation.get("latitude", 0),
                        "longitude": geolocation.get("longitude", 0),
                        "accuracy": geolocation.get("accuracy", 1),
                    })
                else:
                    self._driver.execute_cdp_cmd("Emulation.clearGeolocationOverride", {})
            except Exception:
                pass
        await asyncio.to_thread(_set)

    async def set_offline(self, offline: bool) -> None:
        def _set() -> None:
            try:
                self._driver.execute_cdp_cmd("Network.enable", {})
                self._driver.execute_cdp_cmd("Network.emulateNetworkConditions", {
                    "offline": offline,
                    "latency": 0,
                    "downloadThroughput": -1,
                    "uploadThroughput": -1,
                })
            except Exception:
                pass
        await asyncio.to_thread(_set)

    async def route(self, url: str, handler: Callable[..., Any]) -> None:
        # Selenium does not support network interception natively.
        pass

    async def unroute(self, url: str) -> None:
        pass
