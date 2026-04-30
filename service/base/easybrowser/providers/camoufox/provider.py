from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from ...interfaces.context import BrowserContext
from ...interfaces.provider import BrowserProvider
from ...models.errors import ConnectionError, TimeoutError
from ...models.options import LaunchOptions
from ..common.playwright_context import PlaywrightContext


class CamoufoxProvider(BrowserProvider):
    """Provider adapter for Camoufox via Playwright.

    Launches a camoufox server subprocess and connects via Playwright firefox.connect().
    Reuses the launch logic from the existing CamoufoxRuntime in
    repos/EasyBrowser/providers/camoufox/runtime.py.
    """

    def __init__(self) -> None:
        self._playwright: Any | None = None
        self._browser: Any | None = None
        self._server_process: subprocess.Popen[str] | None = None
        self._ws_endpoint: str = ""
        self._headless: bool = True
        self._os_name: str = "windows"
        self._ws_timeout_ms: int = 60000
        self._connect_timeout_ms: int = 20000

    @property
    def name(self) -> str:
        return "camoufox"

    async def launch(self, options: LaunchOptions | None = None) -> BrowserContext:
        opts = options or LaunchOptions()
        self._headless = opts.headless
        self._os_name = opts.extra.get("os_name", os.getenv("EASYBROWSER_CAMOUFOX_OS", "windows")).strip() or "windows"

        from camoufox.server import LAUNCH_SCRIPT, get_nodejs, to_camel_case_dict
        from camoufox.utils import launch_options as build_camoufox_launch_options

        launch_config = build_camoufox_launch_options(
            headless=self._headless,
            os=self._os_name,
            debug=False,
            main_world_eval=True,
        )
        payload = base64.b64encode(
            json.dumps(to_camel_case_dict(launch_config), default=str).encode("utf-8")
        ).decode("ascii")

        nodejs = get_nodejs()
        server_cwd = Path(nodejs).parent / "package"

        self._server_process = subprocess.Popen(
            [nodejs, str(LAUNCH_SCRIPT)],
            cwd=str(server_cwd),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        if self._server_process.stderr is not None:
            threading.Thread(
                target=self._stream_pipe,
                args=(self._server_process.stderr,),
                daemon=True,
            ).start()

        assert self._server_process.stdin is not None
        self._server_process.stdin.write(payload)
        self._server_process.stdin.close()

        self._ws_endpoint = await asyncio.to_thread(
            self._read_ws_endpoint, self._server_process
        )

        if self._server_process.stdout is not None:
            threading.Thread(
                target=self._stream_pipe,
                args=(self._server_process.stdout,),
                daemon=True,
            ).start()

        from playwright.async_api import async_playwright

        pw = await async_playwright().__aenter__()
        self._playwright = pw
        self._browser = await pw.firefox.connect(
            self._ws_endpoint, timeout=self._connect_timeout_ms
        )

        context = await self._browser.new_context()
        return PlaywrightContext(context)

    async def connect(self, endpoint: str, **kwargs: Any) -> BrowserContext:
        from playwright.async_api import async_playwright

        pw = await async_playwright().__aenter__()
        self._playwright = pw
        self._browser = await pw.firefox.connect(
            endpoint, timeout=kwargs.get("timeout_ms", self._connect_timeout_ms)
        )
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

        if self._server_process:
            try:
                self._server_process.terminate()
                self._server_process.wait(timeout=5)
            except Exception:
                try:
                    self._server_process.kill()
                except Exception:
                    pass
            self._server_process = None

        self._ws_endpoint = ""

    async def is_connected(self) -> bool:
        return self._browser is not None and self._browser.is_connected()

    def capabilities(self) -> dict[str, Any]:
        return {
            "provider": "camoufox",
            "engine": "playwright-firefox",
            "context_isolation": True,
            "headless": True,
            "stealth": True,
            "proxy": True,
            "fingerprint": True,
            "remote_connect": True,
            "os_emulation": True,
        }

    def _read_ws_endpoint(self, process: subprocess.Popen[str]) -> str:
        if process.stdout is None:
            raise ConnectionError("camoufox server did not expose stdout")

        deadline = time.time() + (self._ws_timeout_ms / 1000.0)
        ansi_re = re.compile(r"\x1b\[[0-9;]*m")
        while time.time() < deadline:
            line = process.stdout.readline()
            if line == "":
                if process.poll() is not None:
                    raise ConnectionError("camoufox server exited before exposing websocket endpoint")
                time.sleep(0.1)
                continue
            cleaned = ansi_re.sub("", line).strip()
            match = re.search(r"(ws://\S+)", cleaned)
            if match:
                return match.group(1)
        raise TimeoutError(f"timed out waiting for camoufox websocket endpoint after {self._ws_timeout_ms}ms")

    def _stream_pipe(self, pipe: Any) -> None:
        for raw_line in iter(pipe.readline, ""):
            line = raw_line.strip()
            if line:
                print(f"[camoufox] {line}", flush=True)
