"""Opt-in Chromium transport regression; all traffic stays on loopback."""

from __future__ import annotations

import base64
import contextlib
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote


@unittest.skipUnless(
    os.environ.get("RUN_CHROMIUM_PROXY_INTEGRATION") == "1",
    "requires installed Chromium, chromedriver, and browser runtime dependencies",
)
class ChromiumAuthenticatedProxyTests(unittest.TestCase):
    def test_second_browser_does_not_stop_existing_driver(self) -> None:
        from browser_runtime.driver_factory import create_proxy_extension, new_driver

        drivers = []
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            try:
                with patch.dict(os.environ, {
                    "HEADLESS": "1", "ANONYMOUS_MODE": "0", "USE_UNDETECTED_CHROMEDRIVER": "0",
                    "BROWSER_USE_EASYBROWSER": "0", "BROWSER_CLEAN_STALE_PROFILE_STATE": "1",
                }):
                    for profile in (first, second):
                        driver, _ = new_driver(
                            None, browser_user_data_dir=profile,
                            create_proxy_extension_fn=create_proxy_extension,
                            apply_runtime_stealth_fn=lambda *args, **kwargs: {},
                            resolve_chrome_version_main_fn=lambda: None,
                        )
                        drivers.append(driver)
                        driver.get("data:text/html,<title>isolated browser</title>")
                self.assertEqual(["isolated browser", "isolated browser"], [driver.title for driver in drivers])
            finally:
                for driver in reversed(drivers):
                    with contextlib.suppress(Exception):
                        driver.quit()

    def test_explicit_authenticated_proxy_routes_normal_and_private_sessions(self) -> None:
        from browser_runtime.driver_factory import (
            create_proxy_extension,
            new_driver,
        )

        username, password = "fixture-user", "fixture:p@ssword"
        authorization = "Basic " + base64.b64encode(
            f"{username}:{password}".encode("utf-8")
        ).decode("ascii")
        marker = "authenticated-proxy-reached"
        accepted: list[str] = []

        class ProxyHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                if self.headers.get("Proxy-Authorization") != authorization:
                    self.send_response(407)
                    self.send_header("Proxy-Authenticate", 'Basic realm="fixture"')
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                accepted.append(self.path)
                body = marker.encode("ascii")
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_CONNECT(self) -> None:
                self.send_error(502)

            def log_message(self, _format: str, *args: object) -> None:
                pass

        with ThreadingHTTPServer(("127.0.0.1", 0), ProxyHandler) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            proxy = (
                f"http://{quote(username, safe='')}:{quote(password, safe='')}"
                f"@127.0.0.1:{server.server_port}"
            )
            try:
                for anonymous in ("0", "1"):
                    with self.subTest(anonymous=anonymous), tempfile.TemporaryDirectory() as profile:
                        driver = None
                        env = {
                            "HEADLESS": "1",
                            "ANONYMOUS_MODE": anonymous,
                            "USE_UNDETECTED_CHROMEDRIVER": "0",
                            "BROWSER_USE_EASYBROWSER": "0",
                            "BLOCK_IMAGES": "0",
                            "BLOCK_CSS": "0",
                            "BLOCK_FONTS": "0",
                        }
                        try:
                            with patch.dict(os.environ, env):
                                driver, _ = new_driver(
                                    proxy,
                                    browser_user_data_dir=profile,
                                    create_proxy_extension_fn=create_proxy_extension,
                                    apply_runtime_stealth_fn=lambda *args, **kwargs: {},
                                    resolve_chrome_version_main_fn=lambda: None,
                                )
                            driver.set_page_load_timeout(15)
                            target = f"http://proxy-regression.invalid/case-{anonymous}"
                            driver.get(target)
                            self.assertIn(marker, driver.find_element("tag name", "body").text)
                            self.assertIn(target, accepted)
                            if anonymous == "1":
                                self.assertFalse((Path(profile) / "Default").exists())
                        finally:
                            if driver is not None:
                                with contextlib.suppress(Exception):
                                    driver.quit()
            finally:
                server.shutdown()
                thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
