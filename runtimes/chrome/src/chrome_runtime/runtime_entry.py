"""Runtime entrypoint for the migrated anonymous Chrome stack."""

from __future__ import annotations

import contextlib
import json
import os
import sys
import time
from typing import Any

try:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
except Exception:  # pragma: no cover - handled at runtime
    By = None  # type: ignore
    Keys = None  # type: ignore
    WebDriverWait = None  # type: ignore
    EC = None  # type: ignore

if __package__ is None or __package__ == "":
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from browser_runtime import driver_factory  # type: ignore
from browser_runtime.session_runtime import (  # type: ignore
    BrowserSessionManager,
    run_session_register_auth,
    run_session_register_profile,
    run_session_register_finalize,
    run_session_register_full,
    run_session_repair_login,
    run_session_repair_finalize,
    run_session_repair_full,
)


def parse_args(argv: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    idx = 0
    while idx < len(argv):
        cur = argv[idx]
        if not cur.startswith("--"):
            idx += 1
            continue
        key = cur[2:]
        nxt = argv[idx + 1] if idx + 1 < len(argv) else ""
        if nxt and not nxt.startswith("--"):
            out[key] = nxt
            idx += 2
            continue
        out[key] = "true"
        idx += 1
    return out


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def make_error(category: str, code: str, message: str, retriable: bool, cooldown_candidate: bool, raw: Any = None) -> dict[str, Any]:
    return {
        "category": category,
        "code": code,
        "message": message,
        "retriable": retriable,
        "cooldown_candidate": cooldown_candidate,
        "raw": raw,
    }


def _payload_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _coalesce_string(*values: Any) -> str | None:
    for value in values:
        normalized = str(value or "").strip()
        if normalized:
            return normalized
    return None


def _normalize_auth_error_code(value: str) -> str | None:
    normalized_chars: list[str] = []
    previous_was_separator = False
    for char in str(value or "").strip().lower():
        if char.isalnum():
            normalized_chars.append(char)
            previous_was_separator = False
            continue
        if char == "_" or char in {"-", " ", ":", "/", "."}:
            if normalized_chars and not previous_was_separator:
                normalized_chars.append("_")
                previous_was_separator = True
    normalized = "".join(normalized_chars).strip("_")
    return normalized or None


def _extract_explicit_auth_error_code(message: str) -> str | None:
    lowered = str(message or "").strip().lower()
    if not lowered:
        return None
    if lowered.startswith("auth_error:"):
        return _normalize_auth_error_code(lowered.split(":", 1)[1])

    marker = "an error occurred during authentication"
    marker_index = lowered.find(marker)
    if marker_index < 0:
        return None
    open_index = lowered.find("(", marker_index + len(marker))
    if open_index < 0:
        return None
    close_index = lowered.find(")", open_index + 1)
    if close_index < 0:
        return None
    return _normalize_auth_error_code(lowered[open_index + 1 : close_index])


def _session_page_response(session: Any) -> dict[str, Any]:
    driver = session.driver
    return {
        "id": session.session_id,
        "url": str(getattr(driver, "current_url", "") or ""),
        "title": str(getattr(driver, "title", "") or ""),
    }


def _session_current_url(session: Any) -> str:
    try:
        return str(getattr(session.driver, "current_url", "") or "").strip()
    except Exception:
        return ""


def _session_attach_response(session: Any) -> dict[str, Any] | None:
    driver = session.driver
    capabilities = getattr(driver, "capabilities", None)
    if not isinstance(capabilities, dict):
        return None

    chrome_options = capabilities.get("goog:chromeOptions")
    if not isinstance(chrome_options, dict):
        return None

    debugger_address = str(chrome_options.get("debuggerAddress") or "").strip()
    if not debugger_address:
        return None

    endpoint = debugger_address
    if not endpoint.startswith(("http://", "https://")):
        endpoint = f"http://{endpoint}"

    attach = {
        "scope": "page",
        "transport": "cdp",
        "endpoint": endpoint,
        "browser_name": "chromium",
        "resource_id": session.session_id,
        "page_url": _session_current_url(session),
    }
    return attach


def _session_action_result(session: Any, action: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    result = {
        "action": action,
        "resource_kind": "page",
        "resource_id": session.session_id,
        "response": _session_page_response(session),
    }
    attach = _session_attach_response(session)
    if attach:
        result["attach"] = attach
    if extra:
        result.update(extra)
    return result


def _classify_action_error(message: str) -> tuple[str, str]:
    lowered = str(message or "").strip().lower()
    explicit_auth_error_code = _extract_explicit_auth_error_code(message)
    if explicit_auth_error_code:
        return "auth_error", explicit_auth_error_code
    if "account has been deleted or deactivated" in lowered or "account_deactivated" in lowered:
        return "auth_error", "account_deactivated"
    if "auth_error_during_authentication" in lowered:
        return "auth_error", "auth_error_during_authentication"
    if "auth_error_page" in lowered:
        return "auth_error", "auth_error_page"
    if (
        "blocked" in lowered
        or "captcha" in lowered
        or "turnstile" in lowered
        or "phone number required" in lowered
        or "terms of use" in lowered
    ):
        return "blocked", "action_blocked"
    if (
        "otp" in lowered
        or "verification code" in lowered
        or "code never arrived" in lowered
        or "incorrect code" in lowered
    ):
        if "timeout" in lowered:
            return "otp_timeout", "otp_timeout"
        return "flow_error", "otp_error"
    if "callback" in lowered or "token" in lowered or "auth" in lowered:
        return "auth_error", "callback"
    if "proxy" in lowered or "network" in lowered or "connection" in lowered:
        return "proxy_error", "network"
    return "flow_error", "action_failed"


def _is_retriable_error(category: str, code: str) -> bool:
    normalized_category = str(category or "").strip().lower()
    normalized_code = str(code or "").strip().lower()
    if normalized_category == "auth_error" and normalized_code not in {"callback", "auth_error_page", "auth_error_during_authentication"}:
        return False
    return normalized_category in {"proxy_error", "otp_timeout", "auth_error"}


def _normalized_error_message(message: str, category: str, code: str) -> str:
    normalized_category = str(category or "").strip().lower()
    explicit_auth_error_code = _extract_explicit_auth_error_code(message)
    if normalized_category == "auth_error" and explicit_auth_error_code:
        return explicit_auth_error_code
    return str(message or "")


def _should_mark_runtime_unhealthy(category: str, message: str) -> bool:
    normalized_category = str(category or "").strip().lower()
    normalized_message = str(message or "").strip().lower()
    if normalized_category in {"blocked", "flow_error", "auth_error", "otp_timeout"}:
        return False
    unhealthy_markers = (
        "chrome not reachable",
        "session deleted because of page crash",
        "session deleted because the browser has closed",
        "disconnected: not connected to devtools",
        "devtools",
        "cannot connect to chrome",
        "connection refused",
        "connection reset",
        "broken pipe",
        "invalid session id",
        "timed out receiving message from renderer",
    )
    return any(marker in normalized_message for marker in unhealthy_markers)


class ChromeRuntime:
    def __init__(self, provider_id: str, runtime_id: str) -> None:
        self.provider_id = provider_id
        self.runtime_id = runtime_id
        self.sessions = BrowserSessionManager(default_ttl_seconds=900)
        self.recent_failures = 0

    def send_envelope(self, kind: str, action: str, payload: dict[str, Any], trace: dict[str, Any] | None = None) -> None:
        body = {
            "id": f"msg-{int(time.time() * 1000)}",
            "kind": kind,
            "action": action,
            "timestamp": now_iso(),
            "trace": {
                "runtime_id": self.runtime_id,
                "provider_id": self.provider_id,
                **(trace or {}),
            },
            "payload": payload,
        }
        sys.stdout.write(json.dumps(body) + "\n")
        sys.stdout.flush()

    def send_ready(self) -> None:
        self.send_envelope(
            "event",
            "runtime_ready",
            {
                "runtime_id": self.runtime_id,
                "provider_id": self.provider_id,
                "pid": getattr(sys, "pid", None) or None,
                "state": "ready",
                "started_at": now_iso(),
            },
        )

    def send_heartbeat(self, healthy: bool, notes: str | None = None) -> None:
        self.send_envelope(
            "heartbeat",
            "runtime_health",
            {
                "runtime_id": self.runtime_id,
                "provider_id": self.provider_id,
                "healthy": healthy,
                "timestamp": now_iso(),
                "signals": {
                    "recent_failures": self.recent_failures,
                    "cooldown_active": False,
                },
                "notes": notes,
            },
        )

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
                "finished_at": now_iso(),
            },
            {"task_id": task_id},
        )

    def _find_element(self, driver: Any, target: dict[str, Any]) -> Any:
        if By is None:
            raise RuntimeError("selenium is not available")
        selector = str(target.get("selector") or "").strip()
        xpath = str(target.get("xpath") or "").strip()
        if xpath:
            return driver.find_element(By.XPATH, xpath)
        if selector:
            return driver.find_element(By.CSS_SELECTOR, selector)
        raise RuntimeError("target.selector or target.xpath is required")

    def _wait_for(self, driver: Any, target: dict[str, Any], timeout_s: float) -> Any:
        if WebDriverWait is None or EC is None or By is None:
            raise RuntimeError("selenium is not available")
        selector = str(target.get("selector") or "").strip()
        xpath = str(target.get("xpath") or "").strip()
        url_contains = str(target.get("url_contains") or "").strip()
        wait = WebDriverWait(driver, timeout_s)
        if url_contains:
            return wait.until(lambda d: url_contains in str(getattr(d, "current_url", "") or ""))
        if xpath:
            return wait.until(EC.presence_of_element_located((By.XPATH, xpath)))
        if selector:
            return wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
        raise RuntimeError("wait_for requires target.selector, target.xpath, or target.url_contains")

    def execute_action(self, request: dict[str, Any]) -> dict[str, Any]:
        operation = request.get("operation", {}) if isinstance(request.get("operation"), dict) else {}
        payload = operation.get("payload", {}) if isinstance(operation.get("payload"), dict) else {}
        action = str(payload.get("action") or operation.get("kind") or "").strip()
        if not action:
            raise RuntimeError("missing action")

        if action in ("open_resource", "open_page"):
            url = str(payload.get("startup_url") or payload.get("url") or "about:blank").strip()
            proxy = payload.get("proxy")
            captcha = payload.get("captcha_provider")
            backend = str(payload.get("browser_backend") or "custom").strip()
            session = self.sessions.acquire_session(
                proxy=proxy,
                browser_backend=backend,
                captcha_provider=captcha,
                startup_url=url,
                ttl_seconds=payload.get("ttl_seconds"),
            )
            result = _session_action_result(session, "open_resource")
            result["resource_kind"] = payload.get("resource_kind") or "page"
            return result

        if action in ("close_resource", "close_target"):
            resource_id = str(payload.get("resource_id") or "").strip()
            self.sessions.release_session(resource_id)
            return {
                "action": "close_resource",
                "resource_kind": payload.get("resource_kind") or "page",
                "resource_id": resource_id,
                "response": {"id": resource_id, "status": "closed"},
            }

        if action in ("list_pages", "list_resources"):
            resources = []
            for sess in self.sessions.list_sessions():
                resources.append(
                    {
                        "id": sess.session_id,
                        "url": str(getattr(sess.driver, "current_url", "") or ""),
                        "title": str(getattr(sess.driver, "title", "") or ""),
                        "status": "open",
                    }
                )
            return {
                "action": "list_resources",
                "resource_kind": "page",
                "response": resources,
            }

        if action in ("get_resource", "get_page"):
            resource_id = str(payload.get("resource_id") or "").strip()
            session = self.sessions.get_session(resource_id)
            return _session_action_result(session, "get_resource", {
                "resource_kind": "page",
                "resource_id": resource_id,
            })

        # Actions below require an existing session.
        resource_id = str(payload.get("resource_id") or "").strip()
        session = self.sessions.get_session(resource_id)
        driver = session.driver
        target = _payload_dict(payload.get("target"))
        input_payload = _payload_dict(payload.get("input"))

        if action == "register_auth":
            auth_state = run_session_register_auth(
                session,
                preallocated_email=_coalesce_string(input_payload.get("email")),
                preallocated_session_id=_coalesce_string(input_payload.get("mailbox_session_id"), input_payload.get("mailboxSessionId")),
                preallocated_mailbox_ref=_coalesce_string(input_payload.get("mailbox_ref"), input_payload.get("mailboxRef")),
                captcha_provider=_coalesce_string(input_payload.get("captcha_provider"), input_payload.get("captchaProvider")),
            )
            return _session_action_result(session, action, {
                "state": auth_state,
                "mode": str(auth_state.get("mode") or ""),
                "runner": str(auth_state.get("runner") or ""),
                "email": str(auth_state.get("email") or ""),
            })

        if action == "register_profile":
            profile_state = run_session_register_profile(session)
            return _session_action_result(session, action, {
                "state": profile_state,
                "mode": str(profile_state.get("native_mode") or ""),
                "runner": str(profile_state.get("runner") or ""),
            })

        if action == "register_finalize":
            result = run_session_register_finalize(session)
            finalize_state = session.state.get("register_finalize") if isinstance(session.state, dict) else {}
            return _session_action_result(session, action, {
                "email": result.email,
                "auth": result.auth,
                "mode": str((finalize_state or {}).get("mode") or ""),
                "runner": str((finalize_state or {}).get("runner") or ""),
                "callback_url": str((finalize_state or {}).get("callback_url") or ""),
                "mailbox_ref": str((finalize_state or {}).get("mailbox_ref") or ""),
                "stage1": (finalize_state or {}).get("stage1"),
                "stage2": (finalize_state or {}).get("stage2"),
            })

        if action == "register_full":
            result = run_session_register_full(
                session,
                preallocated_email=_coalesce_string(input_payload.get("email")),
                preallocated_session_id=_coalesce_string(input_payload.get("mailbox_session_id"), input_payload.get("mailboxSessionId")),
                preallocated_mailbox_ref=_coalesce_string(input_payload.get("mailbox_ref"), input_payload.get("mailboxRef")),
                captcha_provider=_coalesce_string(input_payload.get("captcha_provider"), input_payload.get("captchaProvider")),
            )
            register_state = session.state.get("register_result") if isinstance(session.state, dict) else {}
            finalize_state = session.state.get("register_finalize") if isinstance(session.state, dict) else {}
            return _session_action_result(session, action, {
                "email": result.email,
                "auth": result.auth,
                "mode": str((register_state or {}).get("mode") or ""),
                "runner": str((register_state or {}).get("runner") or ""),
                "callback_url": str((finalize_state or {}).get("callback_url") or ""),
                "mailbox_ref": str((finalize_state or {}).get("mailbox_ref") or ""),
                "stage1": (finalize_state or {}).get("stage1"),
                "stage2": (finalize_state or {}).get("stage2"),
            })

        if action == "repair_login":
            repair_state = run_session_repair_login(
                session,
                auth_obj=_payload_dict(input_payload.get("auth")),
                captcha_provider=_coalesce_string(input_payload.get("captcha_provider"), input_payload.get("captchaProvider")),
                browser_backend=_coalesce_string(input_payload.get("browser_backend"), input_payload.get("browserBackend")),
            )
            return _session_action_result(session, action, {
                "state": repair_state,
                "email": str(repair_state.get("email") or ""),
                "mode": str(repair_state.get("mode") or ""),
                "runner": str(repair_state.get("runner") or ""),
                "callback_url": str(repair_state.get("callback_url") or ""),
                "mailbox_ref": str(repair_state.get("mailbox_ref") or ""),
            })

        if action == "repair_finalize":
            result = run_session_repair_finalize(session)
            finalize_state = session.state.get("repair_finalize") if isinstance(session.state, dict) else {}
            return _session_action_result(session, action, {
                "email": result.email,
                "auth": result.auth,
                "mode": str((finalize_state or {}).get("mode") or ""),
                "runner": str((finalize_state or {}).get("runner") or ""),
                "callback_url": str((finalize_state or {}).get("callback_url") or ""),
                "mailbox_ref": str((finalize_state or {}).get("mailbox_ref") or ""),
                "stage1": (finalize_state or {}).get("stage1"),
                "stage2": (finalize_state or {}).get("stage2"),
            })

        if action == "repair_full":
            result = run_session_repair_full(
                session,
                auth_obj=_payload_dict(input_payload.get("auth")),
                captcha_provider=_coalesce_string(input_payload.get("captcha_provider"), input_payload.get("captchaProvider")),
                browser_backend=_coalesce_string(input_payload.get("browser_backend"), input_payload.get("browserBackend")),
            )
            repair_state = session.state.get("repair_result") if isinstance(session.state, dict) else {}
            finalize_state = session.state.get("repair_finalize") if isinstance(session.state, dict) else {}
            return _session_action_result(session, action, {
                "email": result.email,
                "auth": result.auth,
                "mode": str((repair_state or {}).get("mode") or ""),
                "runner": str((repair_state or {}).get("runner") or ""),
                "callback_url": str((finalize_state or {}).get("callback_url") or ""),
                "mailbox_ref": str((finalize_state or {}).get("mailbox_ref") or ""),
                "stage1": (finalize_state or {}).get("stage1"),
                "stage2": (finalize_state or {}).get("stage2"),
            })

        if action == "navigate":
            url = str(payload.get("url") or "").strip()
            if not url:
                raise RuntimeError("navigate requires url")
            driver.get(url)
            return {
                "action": action,
                "resource_kind": "page",
                "resource_id": resource_id,
                "response": {
                    "id": resource_id,
                    "url": str(getattr(driver, "current_url", "") or ""),
                    "title": str(getattr(driver, "title", "") or ""),
                },
            }

        if action == "click":
            el = self._find_element(driver, target)
            el.click()
            return {
                "action": action,
                "resource_kind": "page",
                "resource_id": resource_id,
                "response": {"id": resource_id, "status": "clicked"},
            }

        if action == "input_text":
            value = str(input_payload.get("value") or "")
            el = self._find_element(driver, target)
            el.clear()
            el.send_keys(value)
            return {
                "action": action,
                "resource_kind": "page",
                "resource_id": resource_id,
                "response": {"id": resource_id, "status": "input", "value": value},
            }

        if action == "submit":
            if target:
                el = self._find_element(driver, target)
                el.submit()
            else:
                if Keys is None:
                    raise RuntimeError("selenium is not available")
                driver.switch_to.active_element.send_keys(Keys.ENTER)
            return {
                "action": action,
                "resource_kind": "page",
                "resource_id": resource_id,
                "response": {"id": resource_id, "status": "submitted"},
            }

        if action == "wait_for":
            timeout_s = float(payload.get("timeout_s") or 15)
            self._wait_for(driver, target, timeout_s)
            return {
                "action": action,
                "resource_kind": "page",
                "resource_id": resource_id,
                "response": {"id": resource_id, "status": "ready"},
            }

        if action == "read_value":
            mode = str(input_payload.get("mode") or "text").strip()
            attr = str(input_payload.get("attribute") or "").strip()
            if mode == "title":
                value = str(getattr(driver, "title", "") or "")
            elif mode == "url":
                value = str(getattr(driver, "current_url", "") or "")
            else:
                el = self._find_element(driver, target)
                if mode == "value":
                    value = str(el.get_attribute("value") or "")
                elif mode == "html":
                    value = str(el.get_attribute("innerHTML") or "")
                elif mode == "attribute" and attr:
                    value = str(el.get_attribute(attr) or "")
                else:
                    value = str(el.text or "")
            return {
                "action": action,
                "resource_kind": "page",
                "resource_id": resource_id,
                "response": {"id": resource_id, "value": value},
            }

        if action == "evaluate_script":
            script = str(input_payload.get("script") or "").strip()
            if not script:
                raise RuntimeError("evaluate_script requires input.script")
            arg = input_payload.get("arg")
            value = driver.execute_script(f"return ({script})(arguments[0]);", arg)
            return {
                "action": action,
                "resource_kind": "page",
                "resource_id": resource_id,
                "response": {"id": resource_id, "value": value},
            }

        raise RuntimeError(f"unsupported action: {action}")

    def handle_execute_task(self, payload: dict[str, Any]) -> None:
        task_id = str(payload.get("task_id") or "")
        request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
        try:
            with contextlib.redirect_stdout(sys.stderr):
                result = self.execute_action(request)
            self.recent_failures = 0
            self.send_heartbeat(True)
            self.send_completion(task_id, True, result, None)
        except Exception as exc:
            category, code = _classify_action_error(str(exc))
            err = make_error(
                category,
                code,
                _normalized_error_message(str(exc), category, code),
                _is_retriable_error(category, code),
                category in {"proxy_error", "blocked"},
            )
            if _should_mark_runtime_unhealthy(category, str(exc)):
                self.recent_failures += 1
                self.send_heartbeat(False, notes=str(exc))
            else:
                self.recent_failures = 0
                self.send_heartbeat(True, notes=str(exc))
            self.send_completion(task_id, False, None, err)

    def run(self) -> int:
        self.send_ready()
        self.send_heartbeat(True)
        for line in sys.stdin:
            raw = line.strip()
            if not raw:
                continue
            try:
                env = json.loads(raw)
            except Exception:
                continue
            kind = str(env.get("kind") or "")
            action = str(env.get("action") or "")
            payload = env.get("payload") if isinstance(env.get("payload"), dict) else {}
            if kind == "request" and action == "execute_task":
                self.handle_execute_task(payload)
                continue
            if kind == "request" and action == "shutdown_runtime":
                break
            if kind == "request" and action == "collect_health":
                self.send_heartbeat(True)
        return 0


def main() -> int:
    args = parse_args(sys.argv[1:])
    provider_id = str(args.get("provider") or "").strip()
    runtime_id = str(args.get("runtime-id") or "").strip()
    if not provider_id or not runtime_id:
        sys.stderr.write("chrome runtime requires --provider and --runtime-id\n")
        return 1

    runtime = ChromeRuntime(provider_id, runtime_id)
    return runtime.run()


if __name__ == "__main__":
    raise SystemExit(main())
