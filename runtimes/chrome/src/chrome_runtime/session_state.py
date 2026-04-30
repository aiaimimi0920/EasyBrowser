from __future__ import annotations

import os
import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from . import driver_factory
from .stealth_source import build_stealth_source
from .stealth_helpers import extract_user_agent_bits


def _env_flag(key: str, default: str = "0") -> bool:
    return (os.environ.get(key, default) or default).strip().lower() in ("1", "true", "yes", "on")


def _build_stealth_profile(drv, *, headless: int):
    return driver_factory.build_stealth_profile(
        drv,
        headless=headless,
        detect_runtime_user_agent_fn=lambda d: driver_factory.detect_runtime_user_agent(
            d,
            resolve_chrome_version_main_fn=driver_factory.resolve_chrome_version_main,
            env_flag_fn=_env_flag,
        ),
        extract_user_agent_bits_fn=extract_user_agent_bits,
    )


def _now_ts() -> float:
    return time.time()


def _cleanup_proxy_dir(path: str | None) -> None:
    if not path:
        return
    try:
        shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass


def _close_driver(driver: Any) -> None:
    if driver is None:
        return
    try:
        driver.quit()
    except Exception:
        pass


def _session_current_url(session: "BrowserSession") -> str:
    try:
        return str(getattr(session.driver, "current_url", "") or "").strip()
    except Exception:
        return ""


def _record_session_event(session: "BrowserSession", event: str, **details: Any) -> None:
    try:
        payload = {
            "ts": _now_ts(),
            "event": str(event or "").strip() or "unknown",
            **{key: value for key, value in details.items() if value is not None},
        }
        session.history.append(payload)
        if len(session.history) > 40:
            del session.history[:-20]
    except Exception:
        pass


def _session_state_summary(session: "BrowserSession") -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key in ("register_auth", "register_profile", "register_finalize", "repair_login", "repair_finalize"):
        state = session.state.get(key)
        if isinstance(state, dict):
            summary[key] = {
                "mode": str(state.get("mode") or ""),
                "runner": str(state.get("runner") or ""),
            }
    return summary


@dataclass
class BrowserSession:
    session_id: str
    driver: Any
    proxy_dir: str | None
    proxy: str | None
    browser_backend: str
    captcha_provider: str | None
    created_at: float
    expires_at: float
    state: dict[str, Any] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)
    lock: threading.RLock = field(default_factory=threading.RLock)

    def to_payload(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "proxy": self.proxy,
            "browser_backend": self.browser_backend,
            "captcha_provider": self.captcha_provider,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "state_keys": sorted(self.state.keys()),
            "current_url": _session_current_url(self),
            "state_summary": _session_state_summary(self),
            "history_tail": list(self.history[-8:]),
        }


class BrowserSessionManager:
    def __init__(self, *, default_ttl_seconds: int = 900) -> None:
        self._default_ttl_seconds = max(60, int(default_ttl_seconds or 900))
        self._sessions: dict[str, BrowserSession] = {}
        self._lock = threading.RLock()

    def reap_expired(self) -> int:
        stale_ids: list[str] = []
        with self._lock:
            now_ts = _now_ts()
            for session_id, session in self._sessions.items():
                if session.expires_at <= now_ts:
                    stale_ids.append(session_id)
        for session_id in stale_ids:
            self.release_session(session_id)
        return len(stale_ids)

    def acquire_session(
        self,
        *,
        proxy: str | None = None,
        browser_backend: str | None = None,
        captcha_provider: str | None = None,
        startup_url: str | None = None,
        ttl_seconds: int | None = None,
    ) -> BrowserSession:
        self.reap_expired()
        driver, proxy_dir = driver_factory.new_driver(
            proxy,
            browser_backend=browser_backend,
            startup_url=startup_url or "",
            create_proxy_extension_fn=driver_factory.create_proxy_extension,
            apply_runtime_stealth_fn=lambda d, *, headless=0: driver_factory.apply_runtime_stealth(
                d, headless=headless,
                build_stealth_profile_fn=lambda drv, h: _build_stealth_profile(drv, headless=h),
                build_stealth_source_fn=build_stealth_source,
            ),
            resolve_chrome_version_main_fn=driver_factory.resolve_chrome_version_main,
        )
        session = BrowserSession(
            session_id=f"browser-session-{uuid.uuid4().hex}",
            driver=driver,
            proxy_dir=proxy_dir,
            proxy=proxy,
            browser_backend=(browser_backend or "custom").strip() or "custom",
            captcha_provider=(captcha_provider or "").strip() or None,
            created_at=_now_ts(),
            expires_at=_now_ts() + max(60, int(ttl_seconds or self._default_ttl_seconds)),
        )
        _record_session_event(
            session,
            "session-acquired",
            browser_backend=session.browser_backend,
            captcha_provider=session.captcha_provider,
            startup_url=str(startup_url or "").strip() or None,
        )
        with self._lock:
            self._sessions[session.session_id] = session
        return session

    def get_session(self, session_id: str) -> BrowserSession:
        self.reap_expired()
        with self._lock:
            session = self._sessions.get(str(session_id or "").strip())
        if session is None:
            raise RuntimeError(f"browser session not found: {session_id}")
        return session

    def renew_session(self, session_id: str, *, ttl_seconds: int | None = None) -> BrowserSession:
        session = self.get_session(session_id)
        with session.lock:
            session.expires_at = _now_ts() + max(60, int(ttl_seconds or self._default_ttl_seconds))
            renew_count = int(session.state.get("_renew_count") or 0) + 1
            session.state["_renew_count"] = renew_count
            return session

    def release_session(self, session_id: str) -> bool:
        with self._lock:
            session = self._sessions.pop(str(session_id or "").strip(), None)
        if session is None:
            return False
        with session.lock:
            _record_session_event(session, "session-release", current_url=_session_current_url(session))
            _close_driver(session.driver)
            _cleanup_proxy_dir(session.proxy_dir)
            session.state.clear()
            session.history.clear()
        return True

    def session_count(self) -> int:
        self.reap_expired()
        with self._lock:
            return len(self._sessions)

    def list_sessions(self) -> list[BrowserSession]:
        self.reap_expired()
        with self._lock:
            return list(self._sessions.values())
