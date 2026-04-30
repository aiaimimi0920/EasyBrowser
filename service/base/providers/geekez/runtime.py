#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright


@dataclass
class PageRecord:
    target_id: str
    context: Any
    page: Any
    created_at: str


class GeekezRuntime:
    def __init__(self, provider_id: str, runtime_id: str) -> None:
        self.provider_id = provider_id
        self.runtime_id = runtime_id
        self.recent_failures = 0
        self.running = True
        self.pages: dict[str, PageRecord] = {}
        self.pages_lock = threading.Lock()
        self._playwright_cm = None
        self._playwright = None
        self.browser = None
        self.browser_version = ""
        self.api_port = self.read_int_env("EASYBROWSER_GEEKEZ_API_PORT", 52000)
        self.api_base_url = f"http://127.0.0.1:{self.api_port}"
        self.app_root = Path(os.getenv("EASYBROWSER_GEEKEZ_APP_ROOT", "/opt/geekez-browser")).resolve()
        self.xdg_config_home = Path(os.getenv("XDG_CONFIG_HOME", "/tmp/geekez-config")).resolve()
        self.home_dir = Path(os.getenv("HOME", "/tmp/geekez-home")).resolve()
        self.app_process: subprocess.Popen[str] | None = None
        self.profile_id: str | None = None
        self.debug_port: int | None = None
        self.connect_timeout_ms = self.read_int_env("EASYBROWSER_GEEKEZ_CONNECT_TIMEOUT_MS", 30000)
        self.goto_timeout_ms = self.read_int_env("EASYBROWSER_GEEKEZ_GOTO_TIMEOUT_MS", 30000)
        self.startup_stage = "init"
        self.startup_started_at = time.monotonic()

    def now_iso(self) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def next_id(self, prefix: str) -> str:
        return f"{prefix}-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"

    def read_int_env(self, key: str, default: int) -> int:
        raw = os.getenv(key, "").strip()
        if not raw:
            return default
        try:
            value = int(raw)
        except ValueError:
            return default
        return value if value > 0 else default

    def startup_elapsed_ms(self) -> int:
        return int((time.monotonic() - self.startup_started_at) * 1000)

    def log(self, message: str) -> None:
        sys.stderr.write(f"geekez runtime: {message}\n")
        sys.stderr.flush()

    def log_stage(self, stage: str, **details: Any) -> None:
        self.startup_stage = stage
        suffix = ""
        if details:
            rendered = ", ".join(f"{key}={details[key]}" for key in sorted(details))
            suffix = f" ({rendered})"
        self.log(f"startup stage={stage}{suffix} elapsed_ms={self.startup_elapsed_ms()}")

    def send_envelope(self, kind: str, action: str, payload: dict[str, Any], trace: dict[str, Any] | None = None) -> None:
        envelope = {
            "id": self.next_id(action or kind),
            "kind": kind,
            "action": action,
            "timestamp": self.now_iso(),
            "trace": {
                "runtime_id": self.runtime_id,
                "provider_id": self.provider_id,
            },
            "payload": payload,
        }
        if trace:
            envelope["trace"].update(trace)
        sys.stdout.write(json.dumps(envelope, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    def send_ready(self) -> None:
        self.send_envelope(
            "event",
            "runtime_ready",
            {
                "runtime_id": self.runtime_id,
                "provider_id": self.provider_id,
                "pid": os.getpid(),
                "state": "ready",
                "started_at": self.now_iso(),
            },
        )

    def send_heartbeat(self, healthy: bool, notes: dict[str, Any] | None = None) -> None:
        payload: dict[str, Any] = {
            "runtime_id": self.runtime_id,
            "provider_id": self.provider_id,
            "healthy": healthy,
            "timestamp": self.now_iso(),
            "signals": {
                "recent_failures": self.recent_failures,
                "cooldown_active": False,
            },
        }
        if notes:
            payload["notes"] = notes
        self.send_envelope("heartbeat", "runtime_health", payload)

    def send_completion(self, task_id: str, success: bool, result: dict[str, Any] | None, error: dict[str, Any] | None) -> None:
        self.send_envelope(
            "event",
            "task_completed",
            {
                "runtime_id": self.runtime_id,
                "task_id": task_id,
                "success": success,
                "result": result,
                "error": error,
                "finished_at": self.now_iso(),
            },
            {"task_id": task_id},
        )

    def normalize_error(self, exc: Exception) -> dict[str, Any]:
        easy = getattr(exc, "easybrowser", None)
        if isinstance(easy, dict):
            return {
                "category": easy.get("category", "unknown"),
                "code": easy.get("code", "unknown_error"),
                "message": easy.get("message", str(exc)),
                "retriable": bool(easy.get("retriable", False)),
                "cooldown_candidate": bool(easy.get("cooldown_candidate", False)),
                "raw": easy.get("raw"),
            }
        message = str(exc)
        lowered = message.lower()
        category = "unknown"
        code = "unknown_error"
        retriable = False
        cooldown_candidate = False
        if "execution context was destroyed" in lowered or "element is not enabled" in lowered or "element was detached" in lowered:
            category = "flow_error"
            code = "action_failed"
        elif "locator.click" in lowered or "locator.fill" in lowered or "locator.press" in lowered:
            category = "flow_error"
            code = "action_failed"
        elif "page.goto" in lowered and "timeout" in lowered:
            category = "proxy_error"
            code = "network"
            retriable = True
            cooldown_candidate = True
        elif "target page, context or browser has been closed" in lowered or "browser has been closed" in lowered:
            category = "transport"
            code = "browser_closed"
            retriable = True
            cooldown_candidate = True
        return {
            "category": category,
            "code": code,
            "message": message,
            "retriable": retriable,
            "cooldown_candidate": cooldown_candidate,
        }

    def should_mark_runtime_unhealthy(self, normalized: dict[str, Any]) -> bool:
        category = str(normalized.get("category") or "").strip().lower()
        code = str(normalized.get("code") or "").strip().lower()
        if category in {"blocked", "flow_error", "auth_error", "otp_timeout"}:
            return False
        if category == "proxy_error" and code == "network":
            return False
        return True

    def make_error(
        self,
        *,
        category: str,
        code: str,
        message: str,
        retriable: bool = False,
        cooldown_candidate: bool = False,
        raw: dict[str, Any] | None = None,
    ) -> Exception:
        err = RuntimeError(message)
        setattr(
            err,
            "easybrowser",
            {
                "category": category,
                "code": code,
                "message": message,
                "retriable": retriable,
                "cooldown_candidate": cooldown_candidate,
                "raw": raw,
            },
        )
        return err

    def _settings_candidates(self) -> list[Path]:
        roots = [
            self.xdg_config_home / "GeekEZ Browser" / "BrowserProfiles",
            self.xdg_config_home / "geekez-browser" / "BrowserProfiles",
            self.home_dir / ".config" / "GeekEZ Browser" / "BrowserProfiles",
            self.home_dir / ".config" / "geekez-browser" / "BrowserProfiles",
        ]
        unique: list[Path] = []
        seen: set[str] = set()
        for root in roots:
            key = str(root)
            if key in seen:
                continue
            seen.add(key)
            unique.append(root)
        return unique

    def _prepare_settings(self) -> None:
        settings_payload = {
            "enableRemoteDebugging": True,
            "enableApiServer": True,
            "apiPort": self.api_port,
            "closeBehavior": "quit",
        }
        for root in self._settings_candidates():
            root.mkdir(parents=True, exist_ok=True)
            settings_path = root / "settings.json"
            settings_path.write_text(json.dumps(settings_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _api_json(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.api_base_url}{path}"
        body = None
        headers = {"Content-Type": "application/json"}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(url, data=body, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                raw = response.read().decode("utf-8", errors="ignore")
                return json.loads(raw or "{}")
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="ignore")
            if raw:
                try:
                    return json.loads(raw)
                except Exception:
                    pass
            raise self.make_error(
                category="provider",
                code="api_http_error",
                message=f"GeekEZ API {method} {path} failed with HTTP {exc.code}",
                retriable=False,
                cooldown_candidate=False,
            )
        except Exception as exc:
            raise self.make_error(
                category="startup",
                code="api_unreachable",
                message=f"GeekEZ API request failed: {exc}",
                retriable=True,
                cooldown_candidate=True,
            ) from exc

    def _wait_for_api_ready(self, timeout_seconds: int = 45) -> None:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            try:
                result = self._api_json("GET", "/api/status")
                if isinstance(result, dict) and result.get("success", True):
                    return
            except Exception:
                pass
            if self.app_process is not None and self.app_process.poll() is not None:
                raise self.make_error(
                    category="startup",
                    code="geekez_app_exited",
                    message="GeekEZ Browser exited before API became ready",
                    retriable=True,
                    cooldown_candidate=True,
                )
            time.sleep(1.0)
        raise self.make_error(
            category="startup",
            code="api_ready_timeout",
            message=f"GeekEZ API did not become ready within {timeout_seconds}s",
            retriable=True,
            cooldown_candidate=True,
        )

    def start_app(self) -> None:
        self._prepare_settings()
        self.home_dir.mkdir(parents=True, exist_ok=True)
        self.xdg_config_home.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env["HOME"] = str(self.home_dir)
        env["XDG_CONFIG_HOME"] = str(self.xdg_config_home)
        env.setdefault("PLAYWRIGHT_BROWSERS_PATH", "0")
        env.setdefault("ELECTRON_DISABLE_SECURITY_WARNINGS", "true")
        env.setdefault("CI", "1")

        app_process_args = [
            "xvfb-run",
            "-a",
            os.path.join("node_modules", ".bin", "electron"),
            ".",
            "--no-sandbox",
        ]
        self.log_stage("start_geekez_app", app_root=str(self.app_root), api_port=self.api_port)
        self.app_process = subprocess.Popen(
            app_process_args,
            cwd=str(self.app_root),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self.log_stage("geekez_app_started", pid=self.app_process.pid)
        if self.app_process.stdout is not None:
            threading.Thread(target=self._stream_pipe, args=(self.app_process.stdout, "stdout"), daemon=True).start()
        if self.app_process.stderr is not None:
            threading.Thread(target=self._stream_pipe, args=(self.app_process.stderr, "stderr"), daemon=True).start()
        self._wait_for_api_ready()
        self.log_stage("geekez_api_ready")

    def ensure_browser_connected(self) -> None:
        if self.browser is not None:
            return
        if self.app_process is None:
            self.start_app()

        profile_name = f"easybrowser-{self.runtime_id.lower()}"
        profile_result = self._api_json(
            "POST",
            "/api/profiles",
            {
                "name": profile_name,
                "proxyStr": "direct://",
                "fingerprint": {
                    "resolution": "1365x1024",
                    "language": "en-US",
                },
            },
        )
        profile = profile_result.get("profile", profile_result)
        self.profile_id = str(profile.get("id") or "").strip()
        if not self.profile_id:
            raise self.make_error(
                category="startup",
                code="missing_profile_id",
                message="GeekEZ API did not return a profile id",
                retriable=False,
                cooldown_candidate=False,
                raw={"response": profile_result},
            )

        launch_result = self._api_json("GET", f"/api/open/{urllib.parse.quote(self.profile_id)}")
        remote_port = launch_result.get("remote port") or launch_result.get("remoteDebugPort")
        if not remote_port:
            raise self.make_error(
                category="startup",
                code="missing_debug_port",
                message="GeekEZ launch response did not include a remote debugging port",
                retriable=False,
                cooldown_candidate=False,
                raw={"response": launch_result},
            )
        self.debug_port = int(remote_port)
        self.log_stage("profile_launched", profile_id=self.profile_id, debug_port=self.debug_port)

        self._playwright_cm = sync_playwright()
        self._playwright = self._playwright_cm.start()
        self.browser = self._connect_browser_with_retry()
        try:
            self.browser_version = self.browser.version
        except Exception:
            self.browser_version = ""
        self.log_stage("browser_connected", browser_version=self.browser_version or "unknown")

    def _connect_browser_with_retry(self) -> Any:
        if self._playwright is None or self.debug_port is None:
            raise self.make_error(
                category="startup",
                code="playwright_not_ready",
                message="GeekEZ runtime attempted CDP connect before Playwright was ready",
                retriable=True,
                cooldown_candidate=True,
            )

        deadline = time.time() + max(self.connect_timeout_ms, 1000) / 1000.0
        last_exc: Exception | None = None
        endpoint = f"http://127.0.0.1:{self.debug_port}"
        while time.time() < deadline:
            try:
                return self._playwright.chromium.connect_over_cdp(endpoint)
            except Exception as exc:
                last_exc = exc
                time.sleep(1.0)
        raise self.make_error(
            category="startup",
            code="cdp_connect_timeout",
            message=f"GeekEZ CDP endpoint did not become ready within {self.connect_timeout_ms}ms: {last_exc}",
            retriable=True,
            cooldown_candidate=True,
        )

    def stop_browser(self) -> None:
        self.running = False
        with self.pages_lock:
            records = list(self.pages.values())
            self.pages.clear()
        for record in records:
            try:
                record.page.close()
            except Exception:
                pass
            try:
                record.context.close()
            except Exception:
                pass
        if self.browser is not None:
            try:
                self.browser.close()
            except Exception:
                pass
        if self._playwright_cm is not None:
            try:
                self._playwright_cm.__exit__(None, None, None)
            except Exception:
                pass
        self.browser = None
        self._playwright = None
        self._playwright_cm = None

        if self.profile_id:
            try:
                self._api_json("POST", f"/api/profiles/{urllib.parse.quote(self.profile_id)}/stop")
            except Exception:
                pass
        self.profile_id = None
        self.debug_port = None

        if self.app_process is not None:
            try:
                self.app_process.terminate()
                self.app_process.wait(timeout=10)
            except Exception:
                try:
                    self.app_process.kill()
                except Exception:
                    pass
        self.app_process = None

    def heartbeat_loop(self) -> None:
        while self.running:
            time.sleep(15)
            if not self.running:
                return
            try:
                self.handle_collect_health()
            except Exception as exc:
                sys.stderr.write(f"geekez heartbeat failed: {exc}\n")
                sys.stderr.flush()

    def _stream_pipe(self, pipe: Any, name: str) -> None:
        for raw_line in iter(pipe.readline, ""):
            line = raw_line.strip()
            if line:
                sys.stderr.write(f"geekez app {name}: {line}\n")
                sys.stderr.flush()

    def register_page(self, target_id: str, context: Any, page: Any) -> str:
        def _cleanup(_: Any = None) -> None:
            with self.pages_lock:
                self.pages.pop(target_id, None)

        try:
            page.on("close", _cleanup)
        except Exception:
            pass

        with self.pages_lock:
            self.pages[target_id] = PageRecord(
                target_id=target_id,
                context=context,
                page=page,
                created_at=self.now_iso(),
            )
        return target_id

    def get_page_record(self, target_id: str) -> PageRecord:
        with self.pages_lock:
            record = self.pages.get(target_id)
        if record is None:
            raise self.make_error(
                category="provider",
                code="target_not_found",
                message=f"unknown geekez target_id: {target_id}",
                retriable=False,
                cooldown_candidate=False,
            )
        return record

    def page_view(self, target_id: str, page: Any) -> dict[str, Any]:
        title = ""
        url = ""
        try:
            title = page.title()
        except Exception:
            title = ""
        try:
            url = page.url
        except Exception:
            url = ""
        return {
            "id": target_id,
            "type": "page",
            "title": title,
            "url": url,
        }

    def resolve_selector(self, target: dict[str, Any], input_payload: dict[str, Any]) -> str:
        for candidate in (
            target.get("selector"),
            target.get("css"),
            target.get("locator"),
            input_payload.get("selector"),
        ):
            value = str(candidate or "").strip()
            if value:
                return value
        raise self.make_error(
            category="provider",
            code="missing_selector",
            message="semantic browser step requires target.selector",
            retriable=False,
            cooldown_candidate=False,
        )

    def resolve_page_url(self, target: dict[str, Any], input_payload: dict[str, Any], payload: dict[str, Any]) -> str:
        for candidate in (
            target.get("url"),
            input_payload.get("url"),
            input_payload.get("value"),
            payload.get("url"),
            payload.get("target_url"),
        ):
            value = str(candidate or "").strip()
            if value:
                return value
        return ""

    def build_attach(self, target_id: str, page: Any) -> dict[str, Any]:
        url = ""
        try:
            url = page.url
        except Exception:
            url = ""
        endpoint = f"http://127.0.0.1:{self.debug_port}" if self.debug_port else ""
        return {
            "scope": "browser",
            "transport": "playwright_cdp",
            "endpoint": endpoint,
            "browser_name": "chromium",
            "resource_id": target_id,
            "page_url": url,
        }

    def list_page_views(self) -> list[dict[str, Any]]:
        with self.pages_lock:
            items = list(self.pages.items())
        views: list[dict[str, Any]] = []
        for target_id, record in items:
            views.append(self.page_view(target_id, record.page))
        views.sort(key=lambda item: item.get("id", ""))
        return views

    def _default_context(self) -> Any:
        self.ensure_browser_connected()
        contexts = list(getattr(self.browser, "contexts", []) or [])
        if contexts:
            return contexts[0]
        return self.browser.new_context()

    def execute_action(self, request: dict[str, Any]) -> dict[str, Any]:
        operation = request.get("operation") or {}
        payload = operation.get("payload") or {}
        action = str(payload.get("action") or operation.get("kind") or "").strip().lower()
        resource_kind = str(payload.get("resource_kind") or payload.get("resourceKind") or "").strip().lower()

        if action in {"open_resource", "list_resources", "get_resource", "close_resource"} and resource_kind not in {"", "page"}:
            raise self.make_error(
                category="provider",
                code="unsupported_resource_kind",
                message=f"geekez does not support resource_kind={resource_kind} for action={action}",
                retriable=False,
                cooldown_candidate=False,
            )

        if action in {"get_version", "health"}:
            self.ensure_browser_connected()
            return {
                "action": action,
                "response": {
                    "Browser": self.browser_version or "GeekEZ/unknown",
                    "Provider": "geekez",
                    "Headless": True,
                    "OS": "linux",
                    "DebugPort": self.debug_port,
                },
                "runtime_id": self.runtime_id,
                "provider_id": self.provider_id,
            }

        if action == "list_resources" or action in {"list_pages", "list_targets"}:
            self.ensure_browser_connected()
            return {
                "action": action,
                "resource_kind": "page",
                "response": self.list_page_views(),
                "runtime_id": self.runtime_id,
                "provider_id": self.provider_id,
            }

        if action in {"open_resource", "open_page", "open_url", "create_tab", "new_page"}:
            self.ensure_browser_connected()
            url = str(payload.get("url") or payload.get("target_url") or "about:blank").strip() or "about:blank"
            target_id = self.next_id("page")
            context = self._default_context()
            page = context.new_page()
            self.register_page(target_id, context, page)
            if url and url != "about:blank":
                page.goto(url, wait_until="domcontentloaded", timeout=int(payload.get("timeout_ms") or self.goto_timeout_ms))
            return {
                "action": action,
                "resource_kind": "page",
                "response": self.page_view(target_id, page),
                "attach": self.build_attach(target_id, page),
                "target_id": target_id,
                "runtime_id": self.runtime_id,
                "provider_id": self.provider_id,
            }

        target_id = str(payload.get("resource_id") or payload.get("target_id") or payload.get("targetId") or payload.get("id") or "").strip()
        if action in {"get_resource", "navigate", "click", "input_text", "submit", "wait_for", "read_value", "activate_target", "close_resource", "close_target"} and not target_id:
            raise self.make_error(
                category="provider",
                code="missing_target_id",
                message=f"{action} requires resource_id or target_id",
                retriable=False,
                cooldown_candidate=False,
            )

        if action == "get_resource":
            record = self.get_page_record(target_id)
            return {
                "action": action,
                "resource_kind": "page",
                "response": self.page_view(target_id, record.page),
                "attach": self.build_attach(target_id, record.page),
                "target_id": target_id,
                "runtime_id": self.runtime_id,
                "provider_id": self.provider_id,
            }

        record = self.get_page_record(target_id)
        target = payload.get("target") if isinstance(payload.get("target"), dict) else {}
        input_payload = payload.get("input") if isinstance(payload.get("input"), dict) else {}

        if action == "navigate":
            url = self.resolve_page_url(target, input_payload, payload)
            if not url:
                raise self.make_error(
                    category="provider",
                    code="missing_url",
                    message="navigate requires target.url, input.url, or input.value",
                    retriable=False,
                    cooldown_candidate=False,
                )
            record.page.goto(url, wait_until="domcontentloaded", timeout=int(payload.get("timeout_ms") or self.goto_timeout_ms))
            response = self.page_view(target_id, record.page)
            response["detail"] = "navigated"
            return {
                "action": action,
                "resource_kind": "page",
                "response": response,
                "attach": self.build_attach(target_id, record.page),
                "target_id": target_id,
                "runtime_id": self.runtime_id,
                "provider_id": self.provider_id,
            }

        if action == "click":
            selector = self.resolve_selector(target, input_payload)
            record.page.locator(selector).first.click(timeout=int(payload.get("timeout_ms") or self.goto_timeout_ms))
            response = self.page_view(target_id, record.page)
            response["detail"] = "clicked"
            return {
                "action": action,
                "resource_kind": "page",
                "response": response,
                "attach": self.build_attach(target_id, record.page),
                "target_id": target_id,
                "runtime_id": self.runtime_id,
                "provider_id": self.provider_id,
            }

        if action == "input_text":
            selector = self.resolve_selector(target, input_payload)
            value = str(input_payload.get("value") or payload.get("value") or "").strip()
            record.page.locator(selector).first.fill(value, timeout=int(payload.get("timeout_ms") or self.goto_timeout_ms))
            response = self.page_view(target_id, record.page)
            response["value"] = value
            response["detail"] = "input_filled"
            return {
                "action": action,
                "resource_kind": "page",
                "response": response,
                "attach": self.build_attach(target_id, record.page),
                "target_id": target_id,
                "runtime_id": self.runtime_id,
                "provider_id": self.provider_id,
            }

        if action == "submit":
            selector = str(target.get("selector") or input_payload.get("selector") or "").strip()
            if selector:
                record.page.locator(selector).first.click(timeout=int(payload.get("timeout_ms") or self.goto_timeout_ms))
            else:
                record.page.keyboard.press("Enter")
            response = self.page_view(target_id, record.page)
            response["detail"] = "submitted"
            return {
                "action": action,
                "resource_kind": "page",
                "response": response,
                "attach": self.build_attach(target_id, record.page),
                "target_id": target_id,
                "runtime_id": self.runtime_id,
                "provider_id": self.provider_id,
            }

        if action == "wait_for":
            timeout_ms = int(payload.get("timeout_ms") or input_payload.get("timeout_ms") or self.goto_timeout_ms)
            selector = str(target.get("selector") or input_payload.get("selector") or "").strip()
            text = str(target.get("text") or input_payload.get("text") or "").strip()
            url_contains = str(target.get("url_contains") or input_payload.get("url_contains") or "").strip()
            if selector:
                record.page.locator(selector).first.wait_for(state="visible", timeout=timeout_ms)
            elif text:
                record.page.get_by_text(text).first.wait_for(state="visible", timeout=timeout_ms)
            elif url_contains:
                record.page.wait_for_url(re.compile(f".*{re.escape(url_contains)}.*"), timeout=timeout_ms)
            else:
                raise self.make_error(
                    category="provider",
                    code="missing_wait_target",
                    message="wait_for requires selector, text, or url_contains",
                    retriable=False,
                    cooldown_candidate=False,
                )
            response = self.page_view(target_id, record.page)
            response["detail"] = "wait_satisfied"
            return {
                "action": action,
                "resource_kind": "page",
                "response": response,
                "attach": self.build_attach(target_id, record.page),
                "target_id": target_id,
                "runtime_id": self.runtime_id,
                "provider_id": self.provider_id,
            }

        if action == "read_value":
            mode = str(input_payload.get("mode") or input_payload.get("read") or target.get("mode") or target.get("read") or "").strip().lower()
            if mode in {"", "url"}:
                value = record.page.url
            elif mode == "title":
                value = record.page.title()
            else:
                selector = self.resolve_selector(target, input_payload)
                locator = record.page.locator(selector).first
                if mode in {"value", "input"}:
                    value = locator.input_value(timeout=int(payload.get("timeout_ms") or self.goto_timeout_ms))
                elif mode == "html":
                    value = locator.inner_html(timeout=int(payload.get("timeout_ms") or self.goto_timeout_ms))
                elif mode == "attribute":
                    attribute_name = str(input_payload.get("name") or target.get("name") or target.get("attribute") or "").strip()
                    if not attribute_name:
                        raise self.make_error(
                            category="provider",
                            code="missing_attribute_name",
                            message="read_value mode=attribute requires input.name or target.attribute",
                            retriable=False,
                            cooldown_candidate=False,
                        )
                    value = locator.get_attribute(attribute_name, timeout=int(payload.get("timeout_ms") or self.goto_timeout_ms))
                else:
                    value = locator.inner_text(timeout=int(payload.get("timeout_ms") or self.goto_timeout_ms))
            response = self.page_view(target_id, record.page)
            response["value"] = value
            response["detail"] = "value_read"
            return {
                "action": action,
                "resource_kind": "page",
                "response": response,
                "attach": self.build_attach(target_id, record.page),
                "target_id": target_id,
                "runtime_id": self.runtime_id,
                "provider_id": self.provider_id,
            }

        if action == "evaluate_script":
            script = str(input_payload.get("script") or target.get("script") or "").strip()
            if not script:
                raise self.make_error(
                    category="provider",
                    code="missing_script",
                    message="evaluate_script requires input.script",
                    retriable=False,
                    cooldown_candidate=False,
                )
            value = record.page.evaluate(script, input_payload.get("arg"))
            response = self.page_view(target_id, record.page)
            response["value"] = value
            response["detail"] = "script_evaluated"
            return {
                "action": action,
                "resource_kind": "page",
                "response": response,
                "attach": self.build_attach(target_id, record.page),
                "target_id": target_id,
                "runtime_id": self.runtime_id,
                "provider_id": self.provider_id,
            }

        if action == "activate_target":
            record.page.bring_to_front()
            return {
                "action": action,
                "response": self.page_view(target_id, record.page),
                "target_id": target_id,
                "runtime_id": self.runtime_id,
                "provider_id": self.provider_id,
            }

        if action in {"close_resource", "close_target"}:
            try:
                record.page.close()
            except Exception:
                pass
            with self.pages_lock:
                self.pages.pop(target_id, None)
            return {
                "action": action,
                "resource_kind": "page",
                "response": "Target is closing",
                "target_id": target_id,
                "runtime_id": self.runtime_id,
                "provider_id": self.provider_id,
            }

        raise self.make_error(
            category="provider",
            code="unsupported_action",
            message=f"unsupported geekez action: {action or '<empty>'}",
            retriable=False,
            cooldown_candidate=False,
        )

    def handle_execute(self, envelope: dict[str, Any]) -> None:
        task_id = str(((envelope.get("trace") or {}).get("task_id")) or ((envelope.get("payload") or {}).get("task_id")) or "").strip()
        request = (envelope.get("payload") or {}).get("request") or {}
        try:
            result = self.execute_action(request)
            self.recent_failures = 0
            self.send_heartbeat(
                True,
                {
                    "provider": "geekez",
                    "browser_version": self.browser_version,
                    "debug_port": self.debug_port,
                    "page_count": len(self.pages),
                },
            )
            self.send_completion(task_id, True, result, None)
        except Exception as exc:
            self.recent_failures += 1
            normalized = self.normalize_error(exc)
            healthy = not self.should_mark_runtime_unhealthy(normalized)
            self.send_heartbeat(
                healthy,
                {
                    "provider": "geekez",
                    "browser_version": self.browser_version,
                    "debug_port": self.debug_port,
                    "last_error": normalized["message"],
                },
            )
            self.send_completion(task_id, False, None, normalized)

    def handle_collect_health(self) -> None:
        healthy = self.app_process is not None and self.app_process.poll() is None
        self.send_heartbeat(
            healthy,
            {
                "provider": "geekez",
                "browser_version": self.browser_version,
                "debug_port": self.debug_port,
                "page_count": len(self.pages),
            },
        )

    def run(self) -> int:
        self.log(
            "starting runtime "
            f"provider={self.provider_id} runtime_id={self.runtime_id} "
            f"api_port={self.api_port}"
        )
        self.start_app()
        self.send_ready()
        self.handle_collect_health()

        heartbeat_thread = threading.Thread(target=self.heartbeat_loop, daemon=True)
        heartbeat_thread.start()

        for raw_line in sys.stdin:
            if not self.running:
                break
            line = raw_line.lstrip("\ufeff").strip()
            if not line:
                continue
            try:
                envelope = json.loads(line)
            except json.JSONDecodeError as exc:
                self.recent_failures += 1
                sys.stderr.write(f"geekez runtime failed to parse message: {exc}\n")
                sys.stderr.flush()
                continue

            action = envelope.get("action")
            try:
                if action == "execute_task":
                    self.handle_execute(envelope)
                elif action == "collect_health":
                    self.handle_collect_health()
                elif action == "shutdown_runtime":
                    break
            except Exception as exc:
                self.recent_failures += 1
                sys.stderr.write(f"geekez runtime action={action!r} crashed: {exc}\n")
                sys.stderr.flush()
                if action == "execute_task":
                    task_id = str(((envelope.get("trace") or {}).get("task_id")) or ((envelope.get("payload") or {}).get("task_id")) or "").strip()
                    normalized = self.normalize_error(exc)
                    self.send_heartbeat(False, {"provider": "geekez", "last_error": normalized["message"]})
                    self.send_completion(task_id, False, None, normalized)

        self.stop_browser()
        return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", required=True)
    parser.add_argument("--runtime-id", required=True)
    args = parser.parse_args()
    runtime = GeekezRuntime(provider_id=args.provider, runtime_id=args.runtime_id)

    def _shutdown(*_: Any) -> None:
        runtime.stop_browser()
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    try:
        return runtime.run()
    except Exception as exc:
        sys.stderr.write(f"{exc}\n")
        sys.stderr.flush()
        runtime.stop_browser()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
