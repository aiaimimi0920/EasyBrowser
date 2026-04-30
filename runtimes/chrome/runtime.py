#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any
from pathlib import Path

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from browser_runtime.runtime_entry import create_anonymous_driver


@dataclass
class PageRecord:
    resource_id: str
    handle: str
    created_at: str


class ChromeRuntime:
    def __init__(self, provider_id: str, runtime_id: str) -> None:
        self.provider_id = provider_id
        self.runtime_id = runtime_id
        self.running = True
        self.driver = None
        self.proxy_dir: str | None = None
        self.pages: dict[str, PageRecord] = {}
        self.pages_lock = threading.Lock()
        self.heartbeat_thread: threading.Thread | None = None

    def now_iso(self) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def next_id(self, prefix: str) -> str:
        return f"{prefix}-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"

    def log(self, message: str) -> None:
        sys.stderr.write(f"chrome runtime: {message}\n")
        sys.stderr.flush()

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
        }
        if notes:
            payload["notes"] = notes
        self.send_envelope("heartbeat", "runtime_health", payload)

    def start_heartbeat(self) -> None:
        def _run() -> None:
            while self.running:
                self.send_heartbeat(True)
                time.sleep(5)

        self.heartbeat_thread = threading.Thread(target=_run, daemon=True)
        self.heartbeat_thread.start()

    def bootstrap(self) -> None:
        self.driver, self.proxy_dir = create_anonymous_driver()
        handle = self.driver.current_window_handle
        resource_id = self.next_id("page")
        self.pages[resource_id] = PageRecord(resource_id=resource_id, handle=handle, created_at=self.now_iso())

    def list_pages(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        with self.pages_lock:
            handles = list(self.driver.window_handles)
            handle_to_id = {record.handle: record.resource_id for record in self.pages.values()}
        current = self.driver.current_window_handle
        for handle in handles:
            self.driver.switch_to.window(handle)
            resource_id = handle_to_id.get(handle)
            if not resource_id:
                resource_id = self.next_id("page")
                with self.pages_lock:
                    self.pages[resource_id] = PageRecord(resource_id=resource_id, handle=handle, created_at=self.now_iso())
            items.append({
                "id": resource_id,
                "url": self.driver.current_url,
                "title": self.driver.title,
            })
        self.driver.switch_to.window(current)
        return items

    def find_record(self, resource_id: str) -> PageRecord | None:
        with self.pages_lock:
            return self.pages.get(resource_id)

    def open_page(self, url: str) -> dict[str, Any]:
        self.driver.execute_script("window.open(arguments[0], '_blank');", url)
        handles = self.driver.window_handles
        new_handle = handles[-1]
        self.driver.switch_to.window(new_handle)
        resource_id = self.next_id("page")
        with self.pages_lock:
            self.pages[resource_id] = PageRecord(resource_id=resource_id, handle=new_handle, created_at=self.now_iso())
        return {
            "id": resource_id,
            "url": self.driver.current_url,
            "title": self.driver.title,
        }

    def close_page(self, record: PageRecord) -> dict[str, Any]:
        current = self.driver.current_window_handle
        self.driver.switch_to.window(record.handle)
        url = self.driver.current_url
        title = self.driver.title
        self.driver.close()
        remaining = self.driver.window_handles
        if remaining:
            self.driver.switch_to.window(remaining[0])
        else:
            self.running = False
        if current == record.handle and remaining:
            self.driver.switch_to.window(remaining[0])
        with self.pages_lock:
            self.pages.pop(record.resource_id, None)
        return {
            "id": record.resource_id,
            "url": url,
            "title": title,
        }

    def resolve_selector(self, target: dict[str, Any]) -> tuple[str, str]:
        selector = str(target.get("selector") or "").strip()
        xpath = str(target.get("xpath") or "").strip()
        if xpath:
            return "xpath", xpath
        if selector:
            return "css", selector
        raise RuntimeError("missing selector")

    def find_element(self, target: dict[str, Any]):
        kind, value = self.resolve_selector(target)
        if kind == "xpath":
            return self.driver.find_element(By.XPATH, value)
        return self.driver.find_element(By.CSS_SELECTOR, value)

    def wait_for(self, target: dict[str, Any]) -> None:
        timeout = int(target.get("timeout_seconds") or 15)
        selector = str(target.get("selector") or "").strip()
        text = str(target.get("text") or "").strip()
        url_contains = str(target.get("url_contains") or "").strip()
        wait = WebDriverWait(self.driver, timeout)
        if selector:
            kind, value = self.resolve_selector({"selector": selector, "xpath": target.get("xpath")})
            by = By.XPATH if kind == "xpath" else By.CSS_SELECTOR
            wait.until(EC.presence_of_element_located((by, value)))
            return
        if text:
            wait.until(lambda d: text in (d.page_source or ""))
            return
        if url_contains:
            wait.until(lambda d: url_contains in (d.current_url or ""))
            return
        time.sleep(timeout)

    def read_value(self, target: dict[str, Any], input_data: dict[str, Any]) -> dict[str, Any]:
        mode = str(input_data.get("mode") or target.get("mode") or "title").strip().lower()
        if mode == "title":
            return {"value": self.driver.title}
        if mode == "url":
            return {"value": self.driver.current_url}
        element = self.find_element(target)
        if mode == "text":
            return {"value": element.text}
        if mode == "value":
            return {"value": element.get_attribute("value")}
        if mode == "html":
            return {"value": element.get_attribute("outerHTML")}
        if mode == "attribute":
            name = str(input_data.get("name") or "").strip()
            return {"value": element.get_attribute(name)}
        return {"value": self.driver.title}

    def handle_action(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        resource_kind = str(payload.get("resource_kind") or "page").strip().lower()
        if resource_kind and resource_kind != "page":
            raise RuntimeError("resource_kind must be page for chrome runtime")

        if action in ("health",):
            return {
                "runtime_id": self.runtime_id,
                "provider_id": self.provider_id,
                "healthy": True,
                "supported_actions": [
                    "health",
                    "get_version",
                    "open_resource",
                    "list_resources",
                    "get_resource",
                    "close_resource",
                    "navigate",
                    "click",
                    "input_text",
                    "submit",
                    "wait_for",
                    "read_value",
                ],
            }

        if action == "get_version":
            version = ""
            try:
                version = str(self.driver.capabilities.get("browserVersion") or "")
            except Exception:
                version = ""
            return {"version": version}

        if action in ("list_resources",):
            return {"items": self.list_pages()}

        if action in ("get_resource",):
            rid = str(payload.get("resource_id") or "").strip()
            record = self.find_record(rid)
            if not record:
                raise RuntimeError("resource_id not found")
            self.driver.switch_to.window(record.handle)
            return {"id": record.resource_id, "url": self.driver.current_url, "title": self.driver.title}

        if action in ("open_resource",):
            url = str(payload.get("url") or payload.get("startup_url") or "about:blank")
            return self.open_page(url)

        if action in ("close_resource",):
            rid = str(payload.get("resource_id") or "").strip()
            record = self.find_record(rid)
            if not record:
                raise RuntimeError("resource_id not found")
            return self.close_page(record)

        if action == "navigate":
            rid = str(payload.get("resource_id") or "").strip()
            record = self.find_record(rid)
            if not record:
                raise RuntimeError("resource_id not found")
            url = str(payload.get("url") or "").strip()
            self.driver.switch_to.window(record.handle)
            self.driver.get(url)
            return {"id": record.resource_id, "url": self.driver.current_url, "title": self.driver.title}

        if action == "click":
            self.find_element(payload.get("target") or {}).click()
            return {"ok": True}

        if action == "input_text":
            element = self.find_element(payload.get("target") or {})
            value = str((payload.get("input") or {}).get("value") or "")
            element.clear()
            element.send_keys(value)
            return {"ok": True}

        if action == "submit":
            target = payload.get("target") or {}
            if target:
                self.find_element(target).click()
                return {"ok": True}
            self.driver.switch_to.active_element.send_keys(Keys.ENTER)
            return {"ok": True}

        if action == "wait_for":
            self.wait_for(payload.get("target") or {})
            return {"ok": True}

        if action == "read_value":
            return self.read_value(payload.get("target") or {}, payload.get("input") or {})

        raise RuntimeError(f"unsupported action: {action}")

    def handle_request(self, envelope: dict[str, Any]) -> None:
        action = str(envelope.get("action") or "").strip()
        payload = envelope.get("payload") if isinstance(envelope.get("payload"), dict) else {}
        trace = envelope.get("trace") if isinstance(envelope.get("trace"), dict) else {}
        task_id = str(trace.get("task_id") or "").strip()

        try:
            result = self.handle_action(action, payload)
            self.send_envelope(
                "event",
                "task_completed",
                {
                    "task_id": task_id,
                    "runtime_id": self.runtime_id,
                    "provider_id": self.provider_id,
                    "success": True,
                    "result": result,
                    "finished_at": self.now_iso(),
                },
                trace={"task_id": task_id},
            )
        except Exception as exc:
            self.send_envelope(
                "event",
                "task_completed",
                {
                    "task_id": task_id,
                    "runtime_id": self.runtime_id,
                    "provider_id": self.provider_id,
                    "success": False,
                    "error": {
                        "category": "execution",
                        "code": "runtime_error",
                        "message": str(exc),
                        "retriable": False,
                        "cooldown_candidate": False,
                    },
                    "finished_at": self.now_iso(),
                },
                trace={"task_id": task_id},
            )

    def run(self) -> None:
        self.bootstrap()
        self.send_ready()
        self.start_heartbeat()

        for raw in sys.stdin:
            line = raw.strip()
            if not line:
                continue
            try:
                envelope = json.loads(line)
            except Exception:
                continue
            self.handle_request(envelope)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", required=True)
    parser.add_argument("--runtime-id", required=True)
    args = parser.parse_args()
    runtime = ChromeRuntime(args.provider, args.runtime_id)
    try:
        runtime.run()
    except Exception as exc:
        sys.stderr.write(f"chrome runtime fatal: {exc}\n")
        sys.stderr.flush()
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
