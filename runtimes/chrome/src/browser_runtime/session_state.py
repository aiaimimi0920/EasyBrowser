from __future__ import annotations

import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from .runtime_entry import create_anonymous_driver


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


def _session_startup_user_agent(session: "BrowserSession") -> str | None:
    try:
        return str(session.driver.execute_script("return navigator.userAgent || '';") or "").strip() or None
    except Exception:
        return None


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


def _state_mode(state: Any) -> str | None:
    if not isinstance(state, dict):
        return None
    value = str(state.get("mode") or "").strip()
    return value or None


def _state_runner(state: Any) -> str | None:
    if not isinstance(state, dict):
        return None
    value = str(state.get("runner") or "").strip()
    return value or None


def _session_state_summary(session: "BrowserSession") -> dict[str, Any]:
    summary: dict[str, Any] = {}
    register_auth = session.state.get("register_auth")
    if isinstance(register_auth, dict):
        summary["register_auth"] = {
            "email": str(register_auth.get("email") or ""),
            "mode": _state_mode(register_auth),
            "runner": _state_runner(register_auth),
        }
    register_profile = session.state.get("register_profile")
    if isinstance(register_profile, dict):
        summary["register_profile"] = {
            "birthdate": str(register_profile.get("birthdate") or ""),
            "nativeMode": str(register_profile.get("native_mode") or ""),
            "runner": _state_runner(register_profile),
        }
    register_finalize = session.state.get("register_finalize")
    if isinstance(register_finalize, dict):
        stage1 = register_finalize.get("stage1") if isinstance(register_finalize.get("stage1"), dict) else None
        stage2 = register_finalize.get("stage2") if isinstance(register_finalize.get("stage2"), dict) else None
        summary["register_finalize"] = {
            "callback_url": str(register_finalize.get("callback_url") or ""),
            "mailbox_ref": str(register_finalize.get("mailbox_ref") or ""),
            "runner": _state_runner(register_finalize),
            "stage1": stage1,
            "stage2": stage2,
        }
    repair_login = session.state.get("repair_login")
    if isinstance(repair_login, dict):
        summary["repair_login"] = {
            "mode": _state_mode(repair_login),
            "runner": _state_runner(repair_login),
        }
    repair_finalize = session.state.get("repair_finalize")
    if isinstance(repair_finalize, dict):
        summary["repair_finalize"] = {
            "runner": _state_runner(repair_finalize),
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
        native_camoufox = None
        try:
            candidate = getattr(self.driver, "_neuro_camoufox_native_metadata", None)
            if isinstance(candidate, dict):
                native_camoufox = candidate
        except Exception:
            native_camoufox = None
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
            "native_camoufox": native_camoufox,
        }


class BrowserSessionManager:
    def __init__(
        self,
        *,
        default_ttl_seconds: int = 900,
        driver_factory: Callable[..., tuple[Any, str | None]] | None = None,
    ) -> None:
        self._default_ttl_seconds = max(60, int(default_ttl_seconds or 900))
        self._sessions: dict[str, BrowserSession] = {}
        self._lock = threading.RLock()
        self._driver_factory = driver_factory or (lambda **kwargs: create_anonymous_driver(**kwargs))

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
        driver, proxy_dir = self._driver_factory(
            proxy=proxy,
            browser_backend=(browser_backend or "custom").strip() or "custom",
            startup_url=str(startup_url or "").strip(),
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
        try:
            native_meta = getattr(driver, "_neuro_camoufox_native_metadata", None)
            if isinstance(native_meta, dict):
                session.state["native_camoufox"] = native_meta
        except Exception:
            pass
        _record_session_event(
            session,
            "session-acquired",
            browser_backend=session.browser_backend,
            captcha_provider=session.captcha_provider,
            startup_url=str(startup_url or "").strip() or None,
            startup_user_agent=_session_startup_user_agent(session),
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
            _record_session_event(session, "session-renew", ttl_seconds=ttl_seconds)
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
