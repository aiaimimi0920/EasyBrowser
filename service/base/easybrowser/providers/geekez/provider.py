from __future__ import annotations

import asyncio
import uuid
from typing import Any

from ...interfaces.context import BrowserContext
from ...interfaces.provider import BrowserProvider
from ...models.errors import ConnectionError
from ...models.options import LaunchOptions
from ..common.playwright_context import PlaywrightContext
from .api_client import GeekezApiClient


class GeekezProvider(BrowserProvider):
    """Provider adapter for GeekezBrowser.

    Two-phase connection:
    1. REST API to create/launch a profile (with fingerprint + proxy)
    2. Playwright CDP to connect via the remote debugging port

    Requires GeekezBrowser desktop app to be running with
    enableRemoteDebugging: true in its settings.
    """

    def __init__(self, *, api_base_url: str = "http://127.0.0.1:52000") -> None:
        self._api = GeekezApiClient(api_base_url)
        self._playwright: Any | None = None
        self._browser: Any | None = None
        self._profile_id: str | None = None
        self._debug_port: int | None = None

    @property
    def name(self) -> str:
        return "geekez"

    async def launch(self, options: LaunchOptions | None = None) -> BrowserContext:
        opts = options or LaunchOptions()

        profile_data: dict[str, Any] = {}
        if opts.fingerprint:
            fp: dict[str, Any] = {}
            if opts.fingerprint.timezone:
                fp["timezone"] = opts.fingerprint.timezone
            if opts.fingerprint.locale:
                fp["language"] = opts.fingerprint.locale
            if opts.fingerprint.user_agent:
                fp["userAgent"] = opts.fingerprint.user_agent
            if opts.fingerprint.screen_width and opts.fingerprint.screen_height:
                fp["resolution"] = f"{opts.fingerprint.screen_width}x{opts.fingerprint.screen_height}"
            if fp:
                profile_data["fingerprint"] = fp

        if opts.proxy:
            proxy_str = opts.proxy.server
            if opts.proxy.username and opts.proxy.password:
                proxy_str = f"{opts.proxy.username}:{opts.proxy.password}@{opts.proxy.server}"
            profile_data["proxyStr"] = proxy_str
        else:
            profile_data.setdefault("proxyStr", "direct://")

        profile_name = opts.extra.get("profile_name") or opts.extra.get("profile_id")
        if profile_name:
            # Try to use existing profile
            try:
                existing = await self._api.get_profile(profile_name)
                if existing.get("id"):
                    self._profile_id = existing["id"]
                else:
                    raise KeyError("no id")
            except Exception:
                profile_data["name"] = profile_name
                result = await self._api.create_profile(profile_data)
                if not result.get("success", True):
                    raise ConnectionError(
                        f"GeekezBrowser failed to create profile: {result.get('error', 'unknown error')}"
                    )
                profile = result.get("profile", result)
                self._profile_id = profile.get("id", "")
        else:
            profile_data.setdefault("name", f"easybrowser-{uuid.uuid4().hex[:8]}")
            result = await self._api.create_profile(profile_data)
            if not result.get("success", True):
                raise ConnectionError(
                    f"GeekezBrowser failed to create profile: {result.get('error', 'unknown error')}"
                )
            profile = result.get("profile", result)
            self._profile_id = profile.get("id", "")

        launch_result = await self._api.launch_profile(self._profile_id)
        remote_port = launch_result.get("remote port") or launch_result.get("remoteDebugPort")
        if not remote_port:
            raise ConnectionError(
                "GeekezBrowser did not return a remote debugging port. "
                "Ensure enableRemoteDebugging is enabled in GeekezBrowser settings."
            )
        self._debug_port = int(remote_port)

        # Wait for the browser process + CDP to be ready
        await asyncio.sleep(3.0)

        from playwright.async_api import async_playwright

        pw = await async_playwright().__aenter__()
        self._playwright = pw
        self._browser = await pw.chromium.connect_over_cdp(
            f"http://127.0.0.1:{self._debug_port}"
        )

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

        if self._profile_id:
            try:
                await self._api.stop_profile(self._profile_id)
            except Exception:
                pass

        await self._api.close()

    async def is_connected(self) -> bool:
        return self._browser is not None and self._browser.is_connected()

    def capabilities(self) -> dict[str, Any]:
        return {
            "provider": "geekez",
            "engine": "playwright-cdp",
            "context_isolation": True,
            "headless": False,
            "stealth": True,
            "proxy": True,
            "fingerprint": True,
            "remote_connect": True,
            "xray_proxy": True,
            "extensions": True,
        }
