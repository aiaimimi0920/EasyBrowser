from __future__ import annotations

import asyncio
import importlib
import importlib.util
import os
import sys
from typing import Any

from ...interfaces.context import BrowserContext
from ...interfaces.provider import BrowserProvider
from ...models.errors import ConnectionError
from ...models.options import LaunchOptions
from .context import ChromeContext


class ChromeProvider(BrowserProvider):
    """Provider adapter for Chrome via Selenium/undetected-chromedriver.

    Uses the existing driver factory from repos/chrome/src/browser_runtime/.
    """

    def __init__(self) -> None:
        self._driver: Any | None = None
        self._proxy_dir: str | None = None
        self._context: ChromeContext | None = None

    @property
    def name(self) -> str:
        return "chrome"

    async def launch(self, options: LaunchOptions | None = None) -> BrowserContext:
        opts = options or LaunchOptions()

        def _launch() -> tuple[Any, str | None]:
            # Ensure chrome repo is importable.
            chrome_src_candidates = [
                os.path.abspath(
                    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "chrome", "src")
                ),
                os.path.abspath(
                    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "chrome", "src")
                ),
            ]
            chrome_src = next((candidate for candidate in chrome_src_candidates if os.path.isdir(candidate)), "")
            if not chrome_src:
                raise ConnectionError(
                    "EasyBrowser chrome runtime source not found. "
                    f"Tried: {chrome_src_candidates}"
                )
            create_anonymous_driver = _load_chrome_runtime_entrypoint(chrome_src)

            proxy_str: str | None = None
            if opts.proxy:
                if opts.proxy.username and opts.proxy.password:
                    proxy_str = f"http://{opts.proxy.username}:{opts.proxy.password}@{opts.proxy.server}"
                else:
                    proxy_str = opts.proxy.server

            env_overrides: dict[str, str] = {}
            if opts.headless:
                env_overrides["HEADLESS"] = "1"
            else:
                env_overrides["HEADLESS"] = "0"

            if opts.fingerprint:
                if opts.fingerprint.user_agent:
                    env_overrides["STEALTH_USER_AGENT"] = opts.fingerprint.user_agent
                if opts.fingerprint.locale:
                    env_overrides["STEALTH_ACCEPT_LANGUAGE"] = opts.fingerprint.locale
                    env_overrides["STEALTH_BROWSER_LANG"] = opts.fingerprint.locale
                if opts.fingerprint.webgl_vendor:
                    env_overrides["STEALTH_WEBGL_VENDOR"] = opts.fingerprint.webgl_vendor
                if opts.fingerprint.webgl_renderer:
                    env_overrides["STEALTH_WEBGL_RENDERER"] = opts.fingerprint.webgl_renderer
                if opts.fingerprint.hardware_concurrency:
                    env_overrides["STEALTH_HARDWARE_CONCURRENCY"] = str(opts.fingerprint.hardware_concurrency)
                if opts.fingerprint.screen_width and opts.fingerprint.screen_height:
                    env_overrides["BROWSER_WINDOW_SIZE"] = f"{opts.fingerprint.screen_width},{opts.fingerprint.screen_height}"

            old_env: dict[str, str | None] = {}
            for key, val in env_overrides.items():
                old_env[key] = os.environ.get(key)
                os.environ[key] = val

            try:
                driver, proxy_dir = create_anonymous_driver(
                    proxy=proxy_str,
                    browser_backend="custom",
                    startup_url="",
                    startup_user_agent=opts.fingerprint.user_agent if opts.fingerprint and opts.fingerprint.user_agent else "",
                    browser_user_data_dir=opts.user_data_dir or "",
                )
                return driver, proxy_dir
            finally:
                for key, old_val in old_env.items():
                    if old_val is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = old_val

        self._driver, self._proxy_dir = await asyncio.to_thread(_launch)
        self._context = ChromeContext(self._driver)
        return self._context

    async def connect(self, endpoint: str, **kwargs: Any) -> BrowserContext:
        raise ConnectionError("Chrome Selenium provider does not support remote connection. Use launch() instead.")

    async def close(self) -> None:
        if self._context:
            await self._context.close()
            self._context = None
        self._driver = None

    async def is_connected(self) -> bool:
        if self._driver is None:
            return False
        try:
            _ = self._driver.title
            return True
        except Exception:
            return False

    def capabilities(self) -> dict[str, Any]:
        return {
            "provider": "chrome",
            "engine": "selenium",
            "context_isolation": False,
            "headless": True,
            "stealth": True,
            "proxy": True,
            "fingerprint": True,
            "remote_connect": False,
        }


def _load_chrome_runtime_entrypoint(chrome_src: str) -> Any:
    browser_runtime_pkg_dir = os.path.join(chrome_src, "browser_runtime")
    init_py = os.path.join(browser_runtime_pkg_dir, "__init__.py")
    runtime_entry_py = os.path.join(browser_runtime_pkg_dir, "runtime_entry.py")
    if not os.path.isfile(init_py) or not os.path.isfile(runtime_entry_py):
        raise ConnectionError(
            "EasyBrowser chrome runtime package is incomplete. "
            f"Expected files under: {browser_runtime_pkg_dir}"
        )

    package_name = "easybrowser_embedded_chrome_runtime"
    package = sys.modules.get(package_name)
    if package is None:
        package_spec = importlib.util.spec_from_file_location(
            package_name,
            init_py,
            submodule_search_locations=[browser_runtime_pkg_dir],
        )
        if package_spec is None or package_spec.loader is None:
            raise ConnectionError(f"Unable to create spec for {init_py}")
        package = importlib.util.module_from_spec(package_spec)
        sys.modules[package_name] = package
        package_spec.loader.exec_module(package)

    module_name = f"{package_name}.runtime_entry"
    module = sys.modules.get(module_name)
    if module is None:
        module = importlib.import_module(module_name)
    create_anonymous_driver = getattr(module, "create_anonymous_driver", None)
    if not callable(create_anonymous_driver):
        raise ConnectionError(
            "EasyBrowser chrome runtime entrypoint missing create_anonymous_driver"
        )
    return create_anonymous_driver
