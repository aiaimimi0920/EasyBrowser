"""Opt-in transport checks against loopback origins; no account or Internet traffic."""

from __future__ import annotations

import base64
import contextlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import select
import socket
import ssl
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit


@unittest.skipUnless(os.environ.get("RUN_CHROMIUM_PROXY_INTEGRATION") == "1", "opt-in Chromium fixture")
class ChromiumProxyFailClosedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        root = Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix="proxy-proof-")))
        self.root = root
        self.events: list[tuple[str, bool]] = []
        events = self.events
        authorization = "Basic " + base64.b64encode(b"fixture-user:fixture-pass").decode("ascii")

        class Origin(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                events.append(("origin", bool(self.headers.get("Authorization"))))
                if self.path == "/origin-auth":
                    self.send_response(401)
                    self.send_header("WWW-Authenticate", 'Basic realm="origin"')
                else:
                    self.send_response(200)
                body = b"loopback-origin-reached"
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args: object) -> None:
                pass

        def serve(server):
            self.stack.enter_context(server)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self.stack.callback(thread.join, 5)
            self.stack.callback(server.shutdown)
            return server

        self.origin = serve(ThreadingHTTPServer(("127.0.0.1", 0), Origin))
        subprocess.run([
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
            "-subj", "/CN=proxy-fixture.test", "-keyout", str(root / "key.pem"),
            "-out", str(root / "cert.pem"),
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.load_cert_chain(str(root / "cert.pem"), str(root / "key.pem"))
        secure_origin = ThreadingHTTPServer(("127.0.0.1", 0), Origin)
        secure_origin.socket = tls.wrap_socket(secure_origin.socket, server_side=True)
        self.secure_origin = serve(secure_origin)
        allowed_ports = {self.origin.server_port, self.secure_origin.server_port}

        class Proxy(BaseHTTPRequestHandler):
            def authenticated(self) -> bool:
                valid = self.headers.get("Proxy-Authorization") == authorization
                events.append((self.command, valid))
                if not valid:
                    self.send_response(407)
                    self.send_header("Proxy-Authenticate", 'Basic realm="proxy"')
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                return valid

            def do_GET(self) -> None:
                if not self.authenticated():
                    return
                target = urlsplit(self.path)
                if target.hostname != "proxy-fixture.test" or target.port not in allowed_ports:
                    self.send_error(502)
                    return
                connection = http.client.HTTPConnection("127.0.0.1", target.port, timeout=5)
                try:
                    headers = {"Authorization": self.headers["Authorization"]} if self.headers.get("Authorization") else {}
                    connection.request("GET", target.path or "/", headers=headers)
                    response = connection.getresponse()
                    body = response.read()
                    self.send_response(response.status)
                    for key in ("Content-Type", "WWW-Authenticate"):
                        if response.getheader(key):
                            self.send_header(key, response.getheader(key))
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                finally:
                    connection.close()

            def do_CONNECT(self) -> None:
                if not self.authenticated():
                    return
                target = urlsplit("//" + self.path)
                if target.hostname != "proxy-fixture.test" or target.port not in allowed_ports:
                    self.send_error(502)
                    return
                with socket.create_connection(("127.0.0.1", target.port), timeout=5) as upstream:
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.flush()
                    sockets = (self.connection, upstream)
                    while True:
                        readable, _, _ = select.select(sockets, [], [], 5)
                        if not readable:
                            break
                        for source in readable:
                            data = source.recv(65536)
                            if not data:
                                return
                            (upstream if source is self.connection else self.connection).sendall(data)

            def log_message(self, *_args: object) -> None:
                pass

        self.proxy = serve(ThreadingHTTPServer(("127.0.0.1", 0), Proxy))

    @contextlib.contextmanager
    def browser(self, *, password="fixture-pass", missing_extension=False):
        from browser_runtime import driver_factory as factory

        original_chrome = factory.webdriver.Chrome

        def chrome(*args, **kwargs):
            # Only local fixture DNS and its self-signed certificate are changed.
            kwargs["options"].add_argument("--host-resolver-rules=MAP proxy-fixture.test 127.0.0.1")
            kwargs["options"].add_argument("--ignore-certificate-errors")
            return original_chrome(*args, **kwargs)

        proxy_url = f"http://fixture-user:{password}@127.0.0.1:{self.proxy.server_port}"
        extension = (lambda *_args: str(self.root / "absent-extension")) if missing_extension else factory.create_proxy_extension
        driver = None
        with patch.dict(os.environ, {
            "HEADLESS": "1", "ANONYMOUS_MODE": "0", "USE_UNDETECTED_CHROMEDRIVER": "0",
            "BROWSER_CLEAN_STALE_PROFILE_STATE": "0", "BROWSER_USE_EASYBROWSER": "0",
        }), patch.object(factory.webdriver, "Chrome", chrome):
            try:
                driver, _ = factory.new_driver(
                    proxy_url, browser_user_data_dir=str(self.root / "profile"),
                    create_proxy_extension_fn=extension,
                    apply_runtime_stealth_fn=lambda *_args, **_kwargs: {},
                    resolve_chrome_version_main_fn=lambda: None,
                )
                driver.set_page_load_timeout(8)
                yield driver
            finally:
                if driver is not None:
                    with contextlib.suppress(Exception):
                        driver.quit()

    def target(self, path="/", *, secure=False):
        origin = self.secure_origin if secure else self.origin
        return f"{'https' if secure else 'http'}://proxy-fixture.test:{origin.server_port}{path}"

    def test_http_and_https_reach_the_authenticated_proxy(self):
        with self.browser() as driver:
            driver.get(self.target())
            self.assertIn("loopback-origin-reached", driver.page_source)
            self.assertIn(("GET", True), self.events, "HTTP reached origin without authenticated proxy")
            driver.get(self.target(secure=True))
            self.assertIn("loopback-origin-reached", driver.page_source)
            self.assertIn(("CONNECT", True), self.events, "HTTPS reached origin without authenticated proxy")

    def test_unloadable_extension_cannot_silently_connect_directly(self):
        with self.browser(missing_extension=True) as driver:
            with contextlib.suppress(Exception):
                driver.get(self.target())
        self.assertFalse(any(method == "origin" for method, _ in self.events), "extension failure silently bypassed proxy")
        self.assertIn(("GET", False), self.events)

    def test_wrong_password_cannot_silently_connect_directly(self):
        with self.browser(password="wrong-fixture-password") as driver:
            with contextlib.suppress(Exception):
                driver.get(self.target())
        self.assertFalse(any(method == "origin" for method, _ in self.events), "proxy auth failure silently bypassed proxy")
        self.assertIn(("GET", False), self.events)

    def test_proxy_credentials_are_not_sent_to_origin_authentication(self):
        with self.browser() as driver:
            with contextlib.suppress(Exception):
                driver.get(self.target("/origin-auth"))
        self.assertIn(("GET", True), self.events)
        self.assertIn(("origin", False), self.events)
        self.assertNotIn(("origin", True), self.events)


if __name__ == "__main__":
    unittest.main()
