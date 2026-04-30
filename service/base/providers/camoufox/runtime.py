#!/usr/bin/env python
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

from camoufox.server import LAUNCH_SCRIPT, get_nodejs, to_camel_case_dict
from camoufox.utils import launch_options as build_camoufox_launch_options


@dataclass
class PageRecord:
    target_id: str
    context: Any
    page: Any
    created_at: str


class CamoufoxRuntime:
    def __init__(self, provider_id: str, runtime_id: str) -> None:
        self.provider_id = provider_id
        self.runtime_id = runtime_id
        self.recent_failures = 0
        self.running = True
        self.pages: dict[str, PageRecord] = {}
        self.pages_lock = threading.Lock()
        self.headless = os.getenv("EASYBROWSER_CAMOUFOX_HEADLESS", "true").strip().lower() not in {"0", "false", "no"}
        self.os_name = os.getenv("EASYBROWSER_CAMOUFOX_OS", "windows").strip() or "windows"
        self.ws_timeout_ms = self.read_int_env("EASYBROWSER_CAMOUFOX_WS_TIMEOUT_MS", 60000)
        self.connect_timeout_ms = self.read_int_env("EASYBROWSER_CAMOUFOX_CONNECT_TIMEOUT_MS", 20000)
        self.goto_timeout_ms = self.read_int_env("EASYBROWSER_CAMOUFOX_GOTO_TIMEOUT_MS", 30000)
        self._playwright_cm = None
        self._playwright = None
        self.browser = None
        self.browser_version = ""
        self.ws_endpoint = ""
        self.server_process: subprocess.Popen[str] | None = None
        self.heartbeat_thread = None
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
        sys.stderr.write(f"camoufox runtime: {message}\n")
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
        elif "ns_binding_aborted" in lowered or "maybe frame was detached" in lowered:
            category = "transport"
            code = "navigation_interrupted"
            retriable = True
            cooldown_candidate = False
        elif "unknown camoufox target_id" in lowered:
            category = "transport"
            code = "target_not_found"
            retriable = True
            cooldown_candidate = False
        elif "target crashed" in lowered:
            category = "transport"
            code = "target_crashed"
            retriable = True
            cooldown_candidate = False
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
        if category == "transport" and code in {"navigation_interrupted", "target_not_found", "target_crashed"}:
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

    def _drop_none_values(self, value: Any) -> Any:
        if isinstance(value, dict):
            cleaned: dict[str, Any] = {}
            for key, item in value.items():
                if item is None:
                    continue
                cleaned[key] = self._drop_none_values(item)
            return cleaned
        if isinstance(value, list):
            return [self._drop_none_values(item) for item in value if item is not None]
        return value

    def start_browser(self) -> None:
        self.log_stage(
            "build_launch_options",
            headless=self.headless,
            os=self.os_name,
            ws_timeout_ms=self.ws_timeout_ms,
            connect_timeout_ms=self.connect_timeout_ms,
        )
        launch_config = build_camoufox_launch_options(
            headless=self.headless,
            os=self.os_name,
            debug=False,
            main_world_eval=True,
        )
        launch_config = self._drop_none_values(launch_config)
        payload = base64.b64encode(
            json.dumps(to_camel_case_dict(launch_config), default=str).encode("utf-8")
        ).decode("ascii")
        nodejs = get_nodejs()
        server_cwd = Path(nodejs).parent / "package"
        self.server_process = subprocess.Popen(
            [nodejs, str(LAUNCH_SCRIPT)],
            cwd=str(server_cwd),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self.log_stage("server_process_started", pid=self.server_process.pid)

        if self.server_process.stderr is not None:
            threading.Thread(
                target=self._stream_pipe,
                args=(self.server_process.stderr, "stderr"),
                daemon=True,
            ).start()

        try:
            assert self.server_process.stdin is not None
            self.server_process.stdin.write(payload)
            self.server_process.stdin.close()
            self.log_stage("launch_payload_sent")
            self.ws_endpoint = self._read_ws_endpoint(self.server_process)
            self.log_stage("ws_endpoint_received", ws_endpoint="ready")
            self._playwright_cm = sync_playwright()
            self.log_stage("playwright_context_created")
            self._playwright = self._playwright_cm.start()
            self.log_stage("playwright_started")
            self.browser = self._playwright.firefox.connect(self.ws_endpoint, timeout=self.connect_timeout_ms)
            self.log_stage("browser_connected")
        except Exception as exc:
            self.log(
                f"startup failed stage={self.startup_stage} elapsed_ms={self.startup_elapsed_ms()} error={exc}"
            )
            self.stop_browser()
            raise

        try:
            self.browser_version = self.browser.version
        except Exception:
            self.browser_version = ""
        self.log_stage("browser_ready", browser_version=self.browser_version or "unknown")

        if self.server_process.stdout is not None:
            threading.Thread(
                target=self._stream_pipe,
                args=(self.server_process.stdout, "stdout"),
                daemon=True,
            ).start()

    def stop_browser(self) -> None:
        self.running = False
        with self.pages_lock:
            records = list(self.pages.values())
            self.pages.clear()
        for record in records:
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
        if self.server_process is not None:
            try:
                self.server_process.terminate()
                self.server_process.wait(timeout=5)
            except Exception:
                try:
                    self.server_process.kill()
                except Exception:
                    pass
        self._playwright_cm = None
        self._playwright = None
        self.server_process = None
        self.browser = None
        self.ws_endpoint = ""

    def heartbeat_loop(self) -> None:
        while self.running:
            time.sleep(15)
            if not self.running:
                return
            try:
                self.handle_collect_health()
            except Exception as exc:
                sys.stderr.write(f"camoufox heartbeat failed: {exc}\n")
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

    def page_is_open(self, page: Any) -> bool:
        if page is None:
            return False
        try:
            return not page.is_closed()
        except Exception:
            return False

    def recover_page_record(self, target_id: str) -> PageRecord | None:
        browser = self.browser
        if browser is None:
            return None
        candidates: list[tuple[str, Any, Any]] = []
        try:
            contexts = list(browser.contexts)
        except Exception:
            contexts = []
        for context in contexts:
            try:
                pages = list(context.pages)
            except Exception:
                pages = []
            for page in pages:
                if not self.page_is_open(page):
                    continue
                page_url = ""
                try:
                    page_url = str(page.url or "")
                except Exception:
                    page_url = ""
                candidates.append((page_url, context, page))
        if not candidates:
            return None
        preferred = [item for item in candidates if item[0] and item[0] != "about:blank"]
        _, context, page = (preferred or candidates)[-1]
        self.log(f"recovering missing target_id={target_id} from live page")
        self.register_page(target_id, context, page)
        with self.pages_lock:
            return self.pages.get(target_id)

    def get_page_record(self, target_id: str) -> PageRecord:
        with self.pages_lock:
            record = self.pages.get(target_id)
        if record is not None and not self.page_is_open(record.page):
            with self.pages_lock:
                self.pages.pop(target_id, None)
            record = None
        if record is None:
            record = self.recover_page_record(target_id)
        if record is None:
            raise self.make_error(
                category="provider",
                code="target_not_found",
                message=f"unknown camoufox target_id: {target_id}",
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
        return {
            "scope": "browser",
            "transport": "playwright_ws",
            "endpoint": self.ws_endpoint,
            "browser_name": "firefox",
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

    def execute_action(self, request: dict[str, Any]) -> dict[str, Any]:
        if self.browser is None:
            raise self.make_error(
                category="startup",
                code="browser_not_ready",
                message="camoufox browser is not ready",
                retriable=True,
                cooldown_candidate=True,
            )

        operation = request.get("operation") or {}
        payload = operation.get("payload") or {}
        action = str(payload.get("action") or operation.get("kind") or "").strip().lower()
        resource_kind = str(payload.get("resource_kind") or payload.get("resourceKind") or "").strip().lower()

        if action in {"open_resource", "list_resources", "get_resource", "close_resource"} and resource_kind not in {"", "page"}:
            raise self.make_error(
                category="provider",
                code="unsupported_resource_kind",
                message=f"camoufox does not support resource_kind={resource_kind} for action={action}",
                retriable=False,
                cooldown_candidate=False,
            )

        if action in {"get_version", "health"}:
            return {
                "action": action,
                "response": {
                    "Browser": self.browser_version or "Camoufox/unknown",
                    "Provider": "camoufox",
                    "OS": self.os_name,
                    "Headless": self.headless,
                    "WebSocketEndpoint": self.ws_endpoint,
                },
                "runtime_id": self.runtime_id,
                "provider_id": self.provider_id,
            }

        if action == "list_resources":
            return {
                "action": action,
                "resource_kind": "page",
                "response": self.list_page_views(),
                "runtime_id": self.runtime_id,
                "provider_id": self.provider_id,
            }

        if action in {"list_pages", "list_targets"}:
            return {
                "action": action,
                "response": self.list_page_views(),
                "runtime_id": self.runtime_id,
                "provider_id": self.provider_id,
            }

        if action in {"open_resource", "open_page", "open_url", "create_tab", "new_page"}:
            url = str(payload.get("url") or payload.get("target_url") or "about:blank").strip() or "about:blank"
            target_id = self.next_id("page")
            context = self.browser.new_context()
            context.add_init_script(
                f"window.__easybrowser_resource_id = {json.dumps(target_id)};"
            )
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

        if action == "get_resource":
            target_id = str(payload.get("resource_id") or payload.get("target_id") or payload.get("targetId") or payload.get("id") or "").strip()
            if not target_id:
                raise self.make_error(
                    category="provider",
                    code="missing_target_id",
                    message="get_resource requires resource_id or target_id",
                    retriable=False,
                    cooldown_candidate=False,
                )
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

        if action == "navigate":
            target_id = str(payload.get("resource_id") or payload.get("target_id") or payload.get("targetId") or payload.get("id") or "").strip()
            if not target_id:
                raise self.make_error(
                    category="provider",
                    code="missing_target_id",
                    message="navigate requires resource_id or target_id",
                    retriable=False,
                    cooldown_candidate=False,
                )
            record = self.get_page_record(target_id)
            target = payload.get("target") if isinstance(payload.get("target"), dict) else {}
            input_payload = payload.get("input") if isinstance(payload.get("input"), dict) else {}
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
            target_id = str(payload.get("resource_id") or payload.get("target_id") or payload.get("targetId") or payload.get("id") or "").strip()
            if not target_id:
                raise self.make_error(
                    category="provider",
                    code="missing_target_id",
                    message="click requires resource_id or target_id",
                    retriable=False,
                    cooldown_candidate=False,
                )
            record = self.get_page_record(target_id)
            target = payload.get("target") if isinstance(payload.get("target"), dict) else {}
            input_payload = payload.get("input") if isinstance(payload.get("input"), dict) else {}
            selector = self.resolve_selector(target, input_payload)
            locator = record.page.locator(selector).first
            locator.click(timeout=int(payload.get("timeout_ms") or self.goto_timeout_ms))
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
            target_id = str(payload.get("resource_id") or payload.get("target_id") or payload.get("targetId") or payload.get("id") or "").strip()
            if not target_id:
                raise self.make_error(
                    category="provider",
                    code="missing_target_id",
                    message="input_text requires resource_id or target_id",
                    retriable=False,
                    cooldown_candidate=False,
                )
            record = self.get_page_record(target_id)
            target = payload.get("target") if isinstance(payload.get("target"), dict) else {}
            input_payload = payload.get("input") if isinstance(payload.get("input"), dict) else {}
            selector = self.resolve_selector(target, input_payload)
            value = str(input_payload.get("value") or payload.get("value") or "").strip()
            locator = record.page.locator(selector).first
            locator.fill(value, timeout=int(payload.get("timeout_ms") or self.goto_timeout_ms))
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
            target_id = str(payload.get("resource_id") or payload.get("target_id") or payload.get("targetId") or payload.get("id") or "").strip()
            if not target_id:
                raise self.make_error(
                    category="provider",
                    code="missing_target_id",
                    message="submit requires resource_id or target_id",
                    retriable=False,
                    cooldown_candidate=False,
                )
            record = self.get_page_record(target_id)
            target = payload.get("target") if isinstance(payload.get("target"), dict) else {}
            input_payload = payload.get("input") if isinstance(payload.get("input"), dict) else {}
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
            target_id = str(payload.get("resource_id") or payload.get("target_id") or payload.get("targetId") or payload.get("id") or "").strip()
            if not target_id:
                raise self.make_error(
                    category="provider",
                    code="missing_target_id",
                    message="wait_for requires resource_id or target_id",
                    retriable=False,
                    cooldown_candidate=False,
                )
            record = self.get_page_record(target_id)
            target = payload.get("target") if isinstance(payload.get("target"), dict) else {}
            input_payload = payload.get("input") if isinstance(payload.get("input"), dict) else {}
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
            target_id = str(payload.get("resource_id") or payload.get("target_id") or payload.get("targetId") or payload.get("id") or "").strip()
            if not target_id:
                raise self.make_error(
                    category="provider",
                    code="missing_target_id",
                    message="read_value requires resource_id or target_id",
                    retriable=False,
                    cooldown_candidate=False,
                )
            record = self.get_page_record(target_id)
            target = payload.get("target") if isinstance(payload.get("target"), dict) else {}
            input_payload = payload.get("input") if isinstance(payload.get("input"), dict) else {}
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
            target_id = str(payload.get("resource_id") or payload.get("target_id") or payload.get("targetId") or payload.get("id") or "").strip()
            if not target_id:
                raise self.make_error(
                    category="provider",
                    code="missing_target_id",
                    message="evaluate_script requires resource_id or target_id",
                    retriable=False,
                    cooldown_candidate=False,
                )
            record = self.get_page_record(target_id)
            target = payload.get("target") if isinstance(payload.get("target"), dict) else {}
            input_payload = payload.get("input") if isinstance(payload.get("input"), dict) else {}
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
            target_id = str(payload.get("target_id") or payload.get("targetId") or payload.get("id") or "").strip()
            if not target_id:
                raise self.make_error(
                    category="provider",
                    code="missing_target_id",
                    message="activate_target requires target_id",
                    retriable=False,
                    cooldown_candidate=False,
                )
            record = self.get_page_record(target_id)
            record.page.bring_to_front()
            return {
                "action": action,
                "response": self.page_view(target_id, record.page),
                "target_id": target_id,
                "runtime_id": self.runtime_id,
                "provider_id": self.provider_id,
            }

        if action in {"close_resource", "close_target"}:
            target_id = str(payload.get("resource_id") or payload.get("target_id") or payload.get("targetId") or payload.get("id") or "").strip()
            if not target_id:
                raise self.make_error(
                    category="provider",
                    code="missing_target_id",
                    message=f"{action} requires resource_id or target_id",
                    retriable=False,
                    cooldown_candidate=False,
                )
            record = self.get_page_record(target_id)
            record.context.close()
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
            message=f"unsupported camoufox action: {action or '<empty>'}",
            retriable=False,
            cooldown_candidate=False,
            raw={
                "supported_actions": [
                    "get_version",
                    "health",
                    "open_resource",
                    "list_resources",
                    "get_resource",
                    "close_resource",
                    "list_pages",
                    "list_targets",
                    "open_url",
                    "create_tab",
                    "new_page",
                    "navigate",
                    "click",
                    "input_text",
                    "submit",
                    "wait_for",
                    "read_value",
                    "activate_target",
                    "close_target",
                ]
            },
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
                    "provider": "camoufox",
                    "browser_version": self.browser_version,
                    "ws_endpoint": self.ws_endpoint,
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
                    "provider": "camoufox",
                    "browser_version": self.browser_version,
                    "ws_endpoint": self.ws_endpoint,
                    "last_error": normalized["message"],
                },
            )
            self.send_completion(task_id, False, None, normalized)

    def handle_collect_health(self) -> None:
        healthy = self.browser is not None
        self.send_heartbeat(
            healthy,
            {
                "provider": "camoufox",
                "browser_version": self.browser_version,
                "ws_endpoint": self.ws_endpoint,
                "page_count": len(self.pages),
            },
        )

    def _read_ws_endpoint(self, process: subprocess.Popen[str]) -> str:
        if process.stdout is None:
            raise RuntimeError("camoufox server did not expose stdout")

        deadline = time.time() + (self.ws_timeout_ms / 1000.0)
        ansi_re = re.compile(r"\x1b\[[0-9;]*m")
        while time.time() < deadline:
            line = process.stdout.readline()
            if line == "":
                if process.poll() is not None:
                    raise RuntimeError("camoufox server exited before exposing websocket endpoint")
                time.sleep(0.1)
                continue
            cleaned = ansi_re.sub("", line).strip()
            match = re.search(r"(ws://\S+)", cleaned)
            if match:
                return match.group(1)
        raise RuntimeError(
            f"timed out waiting for camoufox websocket endpoint after {self.ws_timeout_ms}ms"
        )

    def _stream_pipe(self, pipe: Any, name: str) -> None:
        for raw_line in iter(pipe.readline, ""):
            line = raw_line.strip()
            if line:
                sys.stderr.write(f"camoufox server {name}: {line}\n")
                sys.stderr.flush()

    def run(self) -> int:
        self.log(
            "starting runtime "
            f"provider={self.provider_id} runtime_id={self.runtime_id} "
            f"headless={self.headless} os={self.os_name} "
            f"ws_timeout_ms={self.ws_timeout_ms} connect_timeout_ms={self.connect_timeout_ms}"
        )
        self.start_browser()
        self.send_ready()
        self.handle_collect_health()

        self.heartbeat_thread = threading.Thread(target=self.heartbeat_loop, daemon=True)
        self.heartbeat_thread.start()

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
                sys.stderr.write(f"camoufox runtime failed to parse message: {exc}\n")
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
                sys.stderr.write(f"camoufox runtime action={action!r} crashed: {exc}\n")
                sys.stderr.flush()
                if action == "execute_task":
                    task_id = str(((envelope.get("trace") or {}).get("task_id")) or ((envelope.get("payload") or {}).get("task_id")) or "").strip()
                    normalized = self.normalize_error(exc)
                    self.send_heartbeat(False, {"provider": "camoufox", "last_error": normalized["message"]})
                    self.send_completion(task_id, False, None, normalized)

        self.stop_browser()
        return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", required=True)
    parser.add_argument("--runtime-id", required=True)
    args = parser.parse_args()

    runtime = CamoufoxRuntime(provider_id=args.provider, runtime_id=args.runtime_id)

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
