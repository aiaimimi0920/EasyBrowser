from __future__ import annotations

import json
import os
import shutil
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from typing import Any

from . import runner
from .repairer_storage import deep_merge_keep_old_when_missing
from .oauth_flow import generate_oauth_url, generate_chatgpt_web_oauth_url
from .camoufox_native import (
    ensure_native_camoufox_profile_root,
    inspect_about_you_surface_on_driver,
    inspect_register_progress_on_driver,
    native_camoufox_enabled,
    prime_native_camoufox_profile,
)
from .register_auth_flow import run_register_auth_flow
from .register_callback_flow import finish_register_callback
from .register_orchestrator import (
    _is_chatgpt_web_logged_in,
    _is_phone_wall_error,
    _is_terms_block_error,
)
from .register_profile_flow import prepare_register_profile
from .repairer_flow import repairer_drive_login_and_get_callback_url
from shared_mailbox.easy_email_client import find_mailbox_by_email


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
            "mode": _state_mode(register_finalize),
            "runner": _state_runner(register_finalize),
            "nativeCallbackMatched": bool(register_finalize.get("native_callback_state", {}).get("callbackMatched")) if isinstance(register_finalize.get("native_callback_state"), dict) else False,
            "stage1Runner": str(stage1.get("runner") or "") if stage1 else "",
            "stage1CallbackUrl": str(stage1.get("callback_url") or "") if stage1 else "",
            "stage1NativeCallbackMatched": bool(stage1.get("native_callback_state", {}).get("callbackMatched")) if stage1 and isinstance(stage1.get("native_callback_state"), dict) else False,
            "stage2Runner": str(stage2.get("runner") or "") if stage2 else "",
            "stage2CallbackUrl": str(stage2.get("callback_url") or "") if stage2 else "",
            "stage2NativeCallbackMatched": bool(stage2.get("native_callback_state", {}).get("callbackMatched")) if stage2 and isinstance(stage2.get("native_callback_state"), dict) else False,
            "stage2ValidateStatus": str(stage2.get("validate_status") or "") if stage2 else "",
            "stage2TokenExchangeStatus": str(stage2.get("token_exchange_status") or "") if stage2 else "",
            "stage2TokenResponseStatus": str(stage2.get("token_response_status") or "") if stage2 else "",
            "stage2ClaimsStatus": str(stage2.get("claims_status") or "") if stage2 else "",
            "stage2AuthPayloadStatus": str(stage2.get("auth_payload_status") or "") if stage2 else "",
        }
    repair_login = session.state.get("repair_login")
    if isinstance(repair_login, dict):
        summary["repair_login"] = {
            "email": str(repair_login.get("email") or ""),
            "mailbox_ref": str(repair_login.get("mailbox_ref") or ""),
            "callback_url": str(repair_login.get("callback_url") or ""),
            "runner": _state_runner(repair_login),
            "nativeCallbackMatched": bool(repair_login.get("native_callback_state", {}).get("callbackMatched")) if isinstance(repair_login.get("native_callback_state"), dict) else False,
        }
    repair_finalize = session.state.get("repair_finalize")
    if isinstance(repair_finalize, dict):
        stage1 = repair_finalize.get("stage1") if isinstance(repair_finalize.get("stage1"), dict) else None
        stage2 = repair_finalize.get("stage2") if isinstance(repair_finalize.get("stage2"), dict) else None
        summary["repair_finalize"] = {
            "callback_url": str(repair_finalize.get("callback_url") or ""),
            "mailbox_ref": str(repair_finalize.get("mailbox_ref") or ""),
            "mode": _state_mode(repair_finalize),
            "runner": _state_runner(repair_finalize),
            "nativeCallbackMatched": bool(repair_finalize.get("native_callback_state", {}).get("callbackMatched")) if isinstance(repair_finalize.get("native_callback_state"), dict) else False,
            "stage1Runner": str(stage1.get("runner") or "") if stage1 else "",
            "stage1CallbackUrl": str(stage1.get("callback_url") or "") if stage1 else "",
            "stage1NativeCallbackMatched": bool(stage1.get("native_callback_state", {}).get("callbackMatched")) if stage1 and isinstance(stage1.get("native_callback_state"), dict) else False,
            "stage2Runner": str(stage2.get("runner") or "") if stage2 else "",
            "stage2SubmitStatus": str(stage2.get("submit_status") or "") if stage2 else "",
            "stage2Email": str(stage2.get("email") or "") if stage2 else "",
            "stage2ValidateStatus": str(stage2.get("validate_status") or "") if stage2 else "",
            "stage2TokenExchangeStatus": str(stage2.get("token_exchange_status") or "") if stage2 else "",
            "stage2TokenResponseStatus": str(stage2.get("token_response_status") or "") if stage2 else "",
            "stage2ClaimsStatus": str(stage2.get("claims_status") or "") if stage2 else "",
            "stage2AuthPayloadStatus": str(stage2.get("auth_payload_status") or "") if stage2 else "",
        }
    register_full = session.state.get("register_full")
    if isinstance(register_full, dict):
        summary["register_full"] = {
            "email": str(register_full.get("email") or ""),
            "mode": _state_mode(register_full),
            "runner": _state_runner(register_full),
        }
    repair_full = session.state.get("repair_full")
    if isinstance(repair_full, dict):
        summary["repair_full"] = {
            "email": str(repair_full.get("email") or ""),
            "mode": _state_mode(repair_full),
            "runner": _state_runner(repair_full),
        }
    register_result = session.state.get("register_result")
    if isinstance(register_result, dict):
        summary["register_result"] = {
            "email": str(register_result.get("email") or ""),
            "mode": _state_mode(register_result),
            "runner": _state_runner(register_result),
        }
    repair_result = session.state.get("repair_result")
    if isinstance(repair_result, dict):
        summary["repair_result"] = {
            "email": str(repair_result.get("email") or ""),
            "mode": _state_mode(repair_result),
            "runner": _state_runner(repair_result),
        }
    native_camoufox = session.state.get("native_camoufox")
    if isinstance(native_camoufox, dict):
        summary["native_camoufox"] = {
            "reason": str(native_camoufox.get("reason") or ""),
            "startupUrl": str(native_camoufox.get("startupUrl") or ""),
            "currentUrl": str(native_camoufox.get("currentUrl") or ""),
        }
    return summary


def _prime_session_camoufox_for_url(
    session: "BrowserSession",
    *,
    startup_url: str | None,
    reason: str,
) -> dict[str, Any] | None:
    if session.browser_backend != "camoufox" or not native_camoufox_enabled():
        return None
    cleanup_root, profile_dir = ensure_native_camoufox_profile_root()
    try:
        metadata = prime_native_camoufox_profile(
            user_data_dir=profile_dir,
            startup_url=startup_url,
            proxy=session.proxy,
            user_agent=_session_startup_user_agent(session),
        )
    finally:
        try:
            shutil.rmtree(cleanup_root, ignore_errors=True)
        except Exception:
            pass
    metadata = {
        **metadata,
        "reason": reason,
        "isolatedProbe": True,
    }
    try:
        setattr(session.driver, "_neuro_camoufox_native_metadata", metadata)
        setattr(session.driver, "_neuro_browser_startup_url", str(startup_url or "").strip())
    except Exception:
        pass
    session.state["native_camoufox"] = metadata
    return metadata


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
        with runner.driver_init_lock:
            driver, proxy_dir = runner._new_driver(
                proxy,
                browser_backend=browser_backend,
                startup_url_override=startup_url,
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

    def list_sessions(self) -> list[BrowserSession]:
        self.reap_expired()
        with self._lock:
            return list(self._sessions.values())

    def session_count(self) -> int:
        self.reap_expired()
        with self._lock:
            return len(self._sessions)


def _build_register_email_resolver(
    *,
    preallocated_email: str | None = None,
    preallocated_session_id: str | None = None,
    preallocated_mailbox_ref: str | None = None,
):
    def _resolve_email(proxy: str | None = None) -> tuple[str, str]:
        _ = proxy
        if preallocated_email and preallocated_mailbox_ref:
            return str(preallocated_email).strip(), str(preallocated_mailbox_ref).strip()
        if preallocated_email and preallocated_session_id:
            return str(preallocated_email).strip(), f"mail-dispatch:{str(preallocated_session_id).strip()}"
        return runner._get_email(proxy)

    return _resolve_email


def run_session_register_auth(
    session: BrowserSession,
    *,
    preallocated_email: str | None = None,
    preallocated_session_id: str | None = None,
    preallocated_mailbox_ref: str | None = None,
    captcha_provider: str | None = None,
) -> dict[str, Any]:
    with session.lock:
        precomputed_oauth = None
        if session.browser_backend == "camoufox":
            precomputed_oauth = generate_chatgpt_web_oauth_url()
            _prime_session_camoufox_for_url(
                session,
                startup_url=getattr(precomputed_oauth, "auth_url", None),
                reason="register-auth",
            )
        auth_state = run_register_auth_flow(
            session.driver,
            proxy=session.proxy,
            get_email=_build_register_email_resolver(
                preallocated_email=preallocated_email,
                preallocated_session_id=preallocated_session_id,
                preallocated_mailbox_ref=preallocated_mailbox_ref,
            ),
            generate_oauth_url=(lambda **_: precomputed_oauth) if precomputed_oauth is not None else generate_chatgpt_web_oauth_url,
            _dbg=runner._dbg,
            _dump_page_body=runner._dump_page_body,
            _raise_if_browser_network_error=runner._raise_if_browser_network_error,
            smart_wait=runner._smart_wait,
            _click_with_debug=runner._click_with_debug,
            _human_mouse_jitter=runner.human_mouse_jitter,
            _human_type=runner.human_type,
            _human_delay=runner.human_delay,
            generate_pwd=runner.generate_pwd,
            get_oai_code=runner._get_oai_code,
            OTP_TIMEOUT_SECONDS=runner.OTP_TIMEOUT_SECONDS,
            captcha_provider=captcha_provider or session.captcha_provider,
            browser_backend=session.browser_backend,
        )
        session.state["register_auth"] = auth_state
        session.state["register_auth_meta"] = {
            "mode": str(auth_state.get("mode") or ""),
            "runner": str(auth_state.get("runner") or ""),
            "oauth_url": str(getattr(precomputed_oauth, "auth_url", "") or ""),
            "current_url": _session_current_url(session),
            "native_probe": session.state.get("native_camoufox"),
        }
        _record_session_event(
            session,
            "register-auth-complete",
            mode=str(auth_state.get("mode") or "") or None,
            runner=str(auth_state.get("runner") or "") or None,
            email=str(auth_state.get("email") or "") or None,
            current_url=_session_current_url(session),
        )
        return auth_state


def run_session_register_profile(session: BrowserSession) -> dict[str, Any]:
    with session.lock:
        if session.browser_backend == "camoufox":
            _prime_session_camoufox_for_url(
                session,
                startup_url=_session_current_url(session) or "https://auth.openai.com/about-you",
                reason="register-profile",
            )
        profile_state = prepare_register_profile(
            driver=session.driver,
            generate_name=runner.generate_name,
            enter_birthday=runner.enter_birthday,
            click_with_debug=runner._click_with_debug,
            dbg=runner._dbg,
            dump_page_body=runner._dump_page_body,
            fill_about_you_birthday_segments=(
                lambda *, iso_yyyy_mm_dd: runner.fill_about_you_birthday_segments(
                    session.driver,
                    iso_yyyy_mm_dd=iso_yyyy_mm_dd,
                )
            ),
            force_submit_about_you_form=(
                lambda *, full_name, iso_yyyy_mm_dd: runner.force_submit_about_you_form(
                    session.driver,
                    full_name=full_name,
                    iso_yyyy_mm_dd=iso_yyyy_mm_dd,
                )
            ),
        )
        if session.browser_backend == "camoufox":
            try:
                native_surface = inspect_about_you_surface_on_driver(session.driver)
            except Exception:
                native_surface = None
        else:
            native_surface = None
        profile_state = {
            **profile_state,
            "native_mode": str(profile_state.get("native_mode") or ""),
            "runner": str(profile_state.get("runner") or ""),
            "current_url": _session_current_url(session),
            "native_surface": native_surface,
        }
        session.state["register_profile"] = profile_state
        _record_session_event(
            session,
            "register-profile-complete",
            native_mode=str(profile_state.get("native_mode") or "") or None,
            runner=str(profile_state.get("runner") or "") or None,
            current_url=_session_current_url(session),
        )
        return profile_state


def _raise_if_add_phone_page(driver: Any) -> None:
    try:
        current_url = str(getattr(driver, "current_url", "") or "").lower()
        body_text_raw = str(
            driver.execute_script(
                "return (document && document.body && document.body.innerText) ? document.body.innerText : '';"
            )
            or ""
        )
        body_text = body_text_raw.lower()
        title_text = str(
            driver.execute_script("return (document && document.title) ? document.title : '';") or ""
        ).lower()
    except Exception:
        return

    if (
        "/add-phone" in current_url
        or "phone number required" in body_text
        or "phone number required" in title_text
        or "需要手机号" in body_text_raw
        or ("手机" in body_text_raw and "号码" in body_text_raw and "需要" in body_text_raw)
    ):
        raise RuntimeError("Blocked: Phone number required on OpenAI add-phone page.")
    if (
        "auth.openai.com/about-you" in current_url
        and (
            "we can't create your account due to our terms of use" in body_text
            or "we cannot create your account due to our terms of use" in body_text
            or ("terms of use" in body_text and "can't create your account" in body_text)
            or ("terms of use" in body_text and "cannot create your account" in body_text)
        )
    ):
        raise RuntimeError("Blocked: Terms of Use restriction on about-you page.")


def run_session_register_finalize(session: BrowserSession) -> runner.BrowserRegistrationResult:
    with session.lock:
        auth_state = session.state.get("register_auth")
        profile_state = session.state.get("register_profile")
        if not isinstance(auth_state, dict):
            raise RuntimeError("register_auth step must complete before finalize")
        if not isinstance(profile_state, dict):
            raise RuntimeError("register_profile step must complete before finalize")

        email = str(auth_state.get("email") or "")
        address_jwt = str(auth_state.get("address_jwt") or "")
        oauth = auth_state.get("oauth")
        pwd = str(auth_state.get("pwd") or "")
        first_name = str(profile_state.get("first_name") or "")
        last_name = str(profile_state.get("last_name") or "")
        birthdate = str(profile_state.get("birthdate") or "")
        stage2_callback_final = ""
        chosen_mailbox_final = address_jwt
        stage1_finalize = None
        try:
            setattr(session.driver, "_neuro_finalize_callback_state", None)
        except Exception:
            pass

        try:
            finish_register_callback(
                driver=session.driver,
                oauth=oauth,
                proxy=session.proxy,
                address_jwt=address_jwt,
                pwd=pwd,
                first_name=first_name,
                last_name=last_name,
                birthdate=birthdate,
                click_final_continue_if_present=lambda: runner.click_final_continue_if_present(
                    driver=session.driver,
                    dbg_fn=runner._dbg,
                    find_visible_fn=runner.find_visible,
                    click_with_debug_fn=runner._click_with_debug,
                ),
                find_visible=runner.find_visible,
                dbg=runner._dbg,
                dump_page_body=runner._dump_page_body,
                save_error_artifacts=runner._save_error_artifacts,
                submit_callback_url=runner._submit_callback_url,
                before_wait_check_fn=lambda: _raise_if_add_phone_page(session.driver),
                skip_submit=True,
                callback_url_contains="chatgpt.com/api/auth/callback/openai",
            )
            stage1_finalize = _driver_register_finalize_stage(session.driver, "_neuro_register_finalize_stage1")

            codex_oauth = generate_oauth_url()
            if session.browser_backend == "camoufox":
                _prime_session_camoufox_for_url(
                    session,
                    startup_url=getattr(codex_oauth, "auth_url", None),
                    reason="register-finalize",
                )
            try:
                setattr(session.driver, "_neuro_repair_flow_result", None)
            except Exception:
                pass
            stage2_callback_url, chosen_mailbox_ref = repairer_drive_login_and_get_callback_url(
                driver=session.driver,
                oauth=codex_oauth,
                email=email,
                password=pwd,
                mailbox_ref_candidates=[address_jwt],
                captcha_provider=session.captcha_provider,
                browser_backend=session.browser_backend,
                smart_wait=runner._smart_wait,
                click_with_debug=runner._click_with_debug,
                get_mailbox_latest_message_id_by_provider=runner.get_mailbox_latest_message_id_by_provider,
                wait_openai_code_by_provider=runner.wait_openai_code_by_provider,
                mailcreate_base_url=runner.MAILCREATE_BASE_URL,
                mailcreate_custom_auth=runner.MAILCREATE_CUSTOM_AUTH,
                gptmail_base_url=runner.GPTMAIL_BASE_URL,
                gptmail_api_key=runner.GPTMAIL_API_KEY,
                gptmail_keys_file=runner.GPTMAIL_KEYS_FILE,
                mailtm_api_base=runner.MAILTM_API_BASE,
                dump_page_body=runner._dump_page_body,
            )
            stage2_callback_final = str(stage2_callback_url or "")
            chosen_mailbox_final = str(chosen_mailbox_ref or address_jwt or "")

            reg_email, auth_json_text, submit_meta = runner._submit_callback_url(
                callback_url=stage2_callback_url,
                expected_state=codex_oauth.state,
                code_verifier=codex_oauth.code_verifier,
                redirect_uri=codex_oauth.redirect_uri,
                proxy=session.proxy,
                mailbox_ref=(chosen_mailbox_ref or address_jwt),
                password=pwd,
                first_name=first_name,
                last_name=last_name,
                birthdate=birthdate,
                return_metadata=True,
            )
        except RuntimeError as exc:
            if _is_terms_block_error(exc):
                raise
            phone_wall = _is_phone_wall_error(exc)
            chatgpt_web_logged_in = _is_chatgpt_web_logged_in(session.driver)
            if not phone_wall and not chatgpt_web_logged_in:
                raise

            codex_oauth = generate_oauth_url()
            if session.browser_backend == "camoufox":
                _prime_session_camoufox_for_url(
                    session,
                    startup_url=getattr(codex_oauth, "auth_url", None),
                    reason="register-finalize-retry",
                )
            try:
                setattr(session.driver, "_neuro_repair_flow_result", None)
            except Exception:
                pass
            callback_url, chosen_mailbox_ref = repairer_drive_login_and_get_callback_url(
                driver=session.driver,
                oauth=codex_oauth,
                email=email,
                password=pwd,
                mailbox_ref_candidates=[address_jwt],
                captcha_provider=session.captcha_provider,
                browser_backend=session.browser_backend,
                smart_wait=runner._smart_wait,
                click_with_debug=runner._click_with_debug,
                get_mailbox_latest_message_id_by_provider=runner.get_mailbox_latest_message_id_by_provider,
                wait_openai_code_by_provider=runner.wait_openai_code_by_provider,
                mailcreate_base_url=runner.MAILCREATE_BASE_URL,
                mailcreate_custom_auth=runner.MAILCREATE_CUSTOM_AUTH,
                gptmail_base_url=runner.GPTMAIL_BASE_URL,
                gptmail_api_key=runner.GPTMAIL_API_KEY,
                gptmail_keys_file=runner.GPTMAIL_KEYS_FILE,
                mailtm_api_base=runner.MAILTM_API_BASE,
                dump_page_body=runner._dump_page_body,
            )
            stage2_callback_final = str(callback_url or "")
            chosen_mailbox_final = str(chosen_mailbox_ref or address_jwt or "")
            reg_email, auth_json_text, submit_meta = runner._submit_callback_url(
                callback_url=callback_url,
                expected_state=codex_oauth.state,
                code_verifier=codex_oauth.code_verifier,
                redirect_uri=codex_oauth.redirect_uri,
                proxy=session.proxy,
                mailbox_ref=(chosen_mailbox_ref or address_jwt),
                password=pwd,
                first_name=first_name,
                last_name=last_name,
                birthdate=birthdate,
                return_metadata=True,
            )

        repair_flow_result = _driver_repair_flow_result(session.driver)
        native_callback_state = _driver_finalize_callback_state(session.driver)
        stage2_finalize = _driver_register_finalize_stage(session.driver, "_neuro_register_finalize_stage2")
        if isinstance(stage2_finalize, dict):
            stage2_finalize = {
                **stage2_finalize,
                "validate_status": str((submit_meta or {}).get("validateStatus") or ""),
                "token_exchange_status": str((submit_meta or {}).get("tokenExchangeStatus") or ""),
                "token_response_status": str((submit_meta or {}).get("tokenResponseStatus") or ""),
                "claims_status": str((submit_meta or {}).get("claimsStatus") or ""),
                "auth_payload_status": str((submit_meta or {}).get("authPayloadStatus") or ""),
                "email": str((submit_meta or {}).get("email") or reg_email or ""),
            }
        session.state["register_finalize"] = {
            "callback_url": stage2_callback_final,
            "mailbox_ref": chosen_mailbox_final,
            "mode": str((repair_flow_result or {}).get("mode") or ""),
            "runner": str((repair_flow_result or {}).get("runner") or ""),
            "native_callback_state": native_callback_state,
            "stage1": stage1_finalize,
            "stage2": stage2_finalize,
            "current_url": _session_current_url(session),
        }
        auth_json = json.loads(auth_json_text)
        if not isinstance(auth_json, dict):
            raise RuntimeError("session finalize returned invalid auth JSON payload")
        auth_json = _ensure_auth_mailbox_ref(auth_json, chosen_mailbox_final)
        result = runner.BrowserRegistrationResult(email=reg_email, auth=auth_json)
        session.state["register_result"] = {
            "email": result.email,
            "auth": result.auth,
            "mode": str(session.state["register_finalize"].get("mode") or ""),
            "runner": str(session.state["register_finalize"].get("runner") or ""),
        }
        _record_session_event(
            session,
            "register-finalize-complete",
            email=result.email,
            mode=str(session.state["register_finalize"].get("mode") or "") or None,
            runner=str(session.state["register_finalize"].get("runner") or "") or None,
            current_url=_session_current_url(session),
        )
        return result


def run_session_register_full(
    session: BrowserSession,
    *,
    preallocated_email: str | None = None,
    preallocated_session_id: str | None = None,
    preallocated_mailbox_ref: str | None = None,
    captcha_provider: str | None = None,
) -> runner.BrowserRegistrationResult:
    with session.lock:
        for key in ("register_auth", "register_profile", "register_finalize", "register_result", "register_full"):
            session.state.pop(key, None)
        precomputed_oauth = generate_oauth_url() if session.browser_backend == "camoufox" else None
        if precomputed_oauth is not None:
            _prime_session_camoufox_for_url(
                session,
                startup_url=getattr(precomputed_oauth, "auth_url", None),
                reason="register-full",
            )
        for attr_name in (
            "_neuro_register_auth_result",
            "_neuro_register_profile_result",
            "_neuro_repair_flow_result",
            "_neuro_register_finalize_stage1",
            "_neuro_register_finalize_stage2",
            "_neuro_finalize_callback_state",
        ):
            try:
                setattr(session.driver, attr_name, None)
            except Exception:
                pass
        email, auth_json_text = runner._register(
            session.driver,
            session.proxy,
            preallocated_email=preallocated_email,
            preallocated_session_id=preallocated_session_id,
            preallocated_mailbox_ref=preallocated_mailbox_ref,
            captcha_provider=captcha_provider or session.captcha_provider,
            browser_backend=session.browser_backend,
            precomputed_oauth=precomputed_oauth,
        )
        auth_state = _driver_register_flow_result(session.driver, "_neuro_register_auth_result")
        profile_state = _driver_register_flow_result(session.driver, "_neuro_register_profile_result")
        repair_flow_result = _driver_repair_flow_result(session.driver)
        finalize_stage1 = _driver_register_finalize_stage(session.driver, "_neuro_register_finalize_stage1")
        finalize_stage2 = _driver_register_finalize_stage(session.driver, "_neuro_register_finalize_stage2")
        if auth_state:
            session.state["register_auth"] = auth_state
        if profile_state:
            session.state["register_profile"] = {
                **profile_state,
                "native_mode": str(profile_state.get("native_mode") or ""),
                "runner": str(profile_state.get("runner") or ""),
                "current_url": _session_current_url(session),
            }
        finalize_state = {
            "callback_url": str((finalize_stage2 or {}).get("callback_url") or ""),
            "mailbox_ref": str((finalize_stage2 or {}).get("mailbox_ref") or (auth_state or {}).get("address_jwt") or ""),
            "mode": str((finalize_stage2 or {}).get("mode") or (repair_flow_result or {}).get("mode") or ""),
            "runner": str((finalize_stage2 or {}).get("runner") or (repair_flow_result or {}).get("runner") or ""),
            "native_callback_state": (finalize_stage2 or {}).get("native_callback_state"),
            "stage1": finalize_stage1,
            "stage2": finalize_stage2,
            "current_url": _session_current_url(session),
        }
        session.state["register_finalize"] = finalize_state
        auth_json = json.loads(auth_json_text)
        if not isinstance(auth_json, dict):
            raise RuntimeError("session register returned invalid auth JSON payload")
        auth_json = _ensure_auth_mailbox_ref(
            auth_json,
            str(finalize_state.get("mailbox_ref") or (auth_state or {}).get("address_jwt") or ""),
        )
        result = runner.BrowserRegistrationResult(email=email, auth=auth_json)
        runner_name = (
            str(finalize_state.get("runner") or "")
            or str(session.state.get("register_profile", {}).get("runner") or "")
            or str((auth_state or {}).get("runner") or "")
            or ("native-camoufox" if session.browser_backend == "camoufox" else "selenium")
        )
        mode_name = (
            str(finalize_state.get("mode") or "")
            or str(session.state.get("register_profile", {}).get("native_mode") or "")
            or str((auth_state or {}).get("mode") or "")
        )
        session.state["register_result"] = {
            "email": result.email,
            "auth": result.auth,
            "mode": mode_name,
            "runner": runner_name,
        }
        session.state["register_full"] = {
            "email": result.email,
            "mode": mode_name,
            "runner": runner_name,
            "current_url": _session_current_url(session),
        }
        _record_session_event(
            session,
            "register-full-complete",
            email=result.email,
            mode=mode_name or None,
            runner=runner_name or None,
            current_url=_session_current_url(session),
        )
        return result


def summarize_session_exception(exc: Exception) -> dict[str, Any]:
    message = str(exc)
    category, stage = None, None
    try:
        from http_server import _classify_error  # local import to avoid cycle at module load
        category, stage = _classify_error(message)
    except Exception:
        pass
    return {
        "error": message,
        "category": category,
        "stage": stage,
        "traceback": traceback.format_exc(),
    }


def _build_repair_mailbox_ref_candidates(auth_obj: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    mailbox_ref = str(auth_obj.get("mailbox_ref") or "").strip()
    email = str(auth_obj.get("email") or "").strip()
    if mailbox_ref:
        candidates.append(mailbox_ref)
    if email:
        preferred_provider = ""
        if ":" in mailbox_ref:
            preferred_provider = str(mailbox_ref.split(":", 1)[0] or "").strip()
        try:
            recovered_mailbox = find_mailbox_by_email(
                email=email,
                preferred_provider=preferred_provider,
                default_base_url=runner.MAILCREATE_BASE_URL,
                default_custom_auth=runner.MAILCREATE_CUSTOM_AUTH,
            )
        except Exception:
            recovered_mailbox = None
        if recovered_mailbox and str(recovered_mailbox.ref or "").strip():
            candidates.append(str(recovered_mailbox.ref).strip())
        else:
            candidates.append(f"gptmail:{email}")
    seen: set[str] = set()
    return [item for item in candidates if item and (item not in seen and not seen.add(item))]


def _effective_mailbox_ref(*, explicit_ref: str, candidate_refs: list[str], chosen_ref: str) -> str:
    for value in (chosen_ref, explicit_ref, *(candidate_refs or [])):
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _ensure_auth_mailbox_ref(auth_obj: dict[str, Any], mailbox_ref: str) -> dict[str, Any]:
    effective_ref = str(mailbox_ref or "").strip()
    if not effective_ref:
        return auth_obj
    current_ref = str(auth_obj.get("mailbox_ref") or "").strip()
    if current_ref:
        return auth_obj
    return {
        **auth_obj,
        "mailbox_ref": effective_ref,
    }


def _driver_repair_flow_result(driver: Any) -> dict[str, Any] | None:
    try:
        candidate = getattr(driver, "_neuro_repair_flow_result", None)
        if isinstance(candidate, dict):
            return candidate
    except Exception:
        pass
    return None


def _driver_register_flow_result(driver: Any, attr_name: str) -> dict[str, Any] | None:
    try:
        candidate = getattr(driver, attr_name, None)
        if isinstance(candidate, dict):
            return candidate
    except Exception:
        pass
    return None


def _driver_finalize_callback_state(driver: Any) -> dict[str, Any] | None:
    try:
        candidate = getattr(driver, "_neuro_finalize_callback_state", None)
        if isinstance(candidate, dict):
            return candidate
    except Exception:
        pass
    return None


def _driver_register_finalize_stage(driver: Any, attr_name: str) -> dict[str, Any] | None:
    try:
        candidate = getattr(driver, attr_name, None)
        if isinstance(candidate, dict):
            return candidate
    except Exception:
        pass
    return None


def run_session_repair_login(
    session: BrowserSession,
    *,
    auth_obj: dict[str, Any],
    captcha_provider: str | None = None,
    browser_backend: str | None = None,
) -> dict[str, Any]:
    if not isinstance(auth_obj, dict):
        raise RuntimeError("repair login requires auth object")
    with session.lock:
        email = str(auth_obj.get("email") or "").strip()
        password = str(auth_obj.get("password") or "").strip()
        mailbox_ref = str(auth_obj.get("mailbox_ref") or "").strip()
        if not email:
            raise RuntimeError("repair login missing email")
        if not password:
            raise RuntimeError("repair login missing password")
        oauth = generate_oauth_url()
        if session.browser_backend == "camoufox":
            _prime_session_camoufox_for_url(
                session,
                startup_url=getattr(oauth, "auth_url", None),
                reason="repair-login",
            )
        try:
            setattr(session.driver, "_neuro_repair_flow_result", None)
        except Exception:
            pass
        try:
            setattr(session.driver, "_neuro_finalize_callback_state", None)
        except Exception:
            pass
        candidates = _build_repair_mailbox_ref_candidates(auth_obj)
        callback_url, chosen_ref = repairer_drive_login_and_get_callback_url(
            driver=session.driver,
            oauth=oauth,
            email=email,
            password=password,
            mailbox_ref_candidates=candidates,
            captcha_provider=captcha_provider or session.captcha_provider,
            browser_backend=browser_backend or session.browser_backend,
            smart_wait=runner._smart_wait,
            click_with_debug=runner._click_with_debug,
            get_mailbox_latest_message_id_by_provider=runner.get_mailbox_latest_message_id_by_provider,
            wait_openai_code_by_provider=runner.wait_openai_code_by_provider,
            mailcreate_base_url=runner.MAILCREATE_BASE_URL,
            mailcreate_custom_auth=runner.MAILCREATE_CUSTOM_AUTH,
            gptmail_base_url=runner.GPTMAIL_BASE_URL,
            gptmail_api_key=runner.GPTMAIL_API_KEY,
            gptmail_keys_file=runner.GPTMAIL_KEYS_FILE,
            mailtm_api_base=runner.MAILTM_API_BASE,
            dump_page_body=runner._dump_page_body,
        )
        repair_flow_result = _driver_repair_flow_result(session.driver)
        effective_mailbox_ref = _effective_mailbox_ref(
            explicit_ref=mailbox_ref,
            candidate_refs=candidates,
            chosen_ref=chosen_ref,
        )
        state = {
            "email": email,
            "password": password,
            "oauth": oauth,
            "callback_url": callback_url,
            "mailbox_ref": effective_mailbox_ref,
            "auth_source": _ensure_auth_mailbox_ref(auth_obj, effective_mailbox_ref),
            "current_url": _session_current_url(session),
            "mode": str((repair_flow_result or {}).get("mode") or ""),
            "runner": str((repair_flow_result or {}).get("runner") or ""),
            "native_callback_state": _driver_finalize_callback_state(session.driver),
        }
        if session.browser_backend == "camoufox":
            try:
                state["native_progress"] = inspect_register_progress_on_driver(
                    session.driver,
                    callback_url_contains="localhost:1455",
                )
            except Exception:
                pass
        session.state["repair_login"] = state
        _record_session_event(
            session,
            "repair-login-complete",
            email=email,
            mailbox_ref=effective_mailbox_ref,
            mode=str(state.get("mode") or "") or None,
            runner=str(state.get("runner") or "") or None,
            current_url=_session_current_url(session),
        )
        return {
            "email": email,
            "callback_url": callback_url,
            "mailbox_ref": effective_mailbox_ref,
            "mode": str(state.get("mode") or ""),
            "runner": str(state.get("runner") or ""),
        }


def run_session_repair_finalize(session: BrowserSession) -> runner.BrowserRegistrationResult:
    with session.lock:
        state = session.state.get("repair_login")
        if not isinstance(state, dict):
            raise RuntimeError("repair_login step must complete before repair finalize")
        oauth = state.get("oauth")
        callback_url = str(state.get("callback_url") or "").strip()
        password = str(state.get("password") or "").strip()
        mailbox_ref = str(state.get("mailbox_ref") or "").strip()
        auth_source = state.get("auth_source")
        if not callback_url:
            raise RuntimeError("repair finalize missing callback_url")
        if not password:
            raise RuntimeError("repair finalize missing password")
        if not isinstance(auth_source, dict):
            raise RuntimeError("repair finalize missing auth source")

        reg_email, auth_json_text, submit_meta = runner._submit_callback_url(
            callback_url=callback_url,
            expected_state=oauth.state,
            code_verifier=oauth.code_verifier,
            redirect_uri=oauth.redirect_uri,
            proxy=session.proxy,
            mailbox_ref=mailbox_ref,
            password=password,
            first_name=str(auth_source.get("first_name") or ""),
            last_name=str(auth_source.get("last_name") or ""),
            birthdate=str(auth_source.get("birthdate") or ""),
            return_metadata=True,
        )
        auth_json = json.loads(auth_json_text)
        if not isinstance(auth_json, dict):
            raise RuntimeError("repair finalize returned invalid auth JSON payload")
        merged = deep_merge_keep_old_when_missing(auth_source, auth_json)
        if isinstance(merged, dict):
            merged = _ensure_auth_mailbox_ref(merged, mailbox_ref)
        result = runner.BrowserRegistrationResult(email=reg_email, auth=merged)
        native_callback_state = _driver_finalize_callback_state(session.driver)
        stage1_state = {
            "callback_url": callback_url,
            "mailbox_ref": mailbox_ref,
            "mode": str(state.get("mode") or ""),
            "runner": str(state.get("runner") or ""),
            "native_callback_state": state.get("native_callback_state"),
        }
        stage2_state = {
            "callback_url": callback_url,
            "mailbox_ref": mailbox_ref,
            "submit_status": "ok",
            "runner": "submit-callback-url",
            "email": result.email,
            "validate_status": str((submit_meta or {}).get("validateStatus") or ""),
            "token_exchange_status": str((submit_meta or {}).get("tokenExchangeStatus") or ""),
            "token_response_status": str((submit_meta or {}).get("tokenResponseStatus") or ""),
            "claims_status": str((submit_meta or {}).get("claimsStatus") or ""),
            "auth_payload_status": str((submit_meta or {}).get("authPayloadStatus") or ""),
        }
        session.state["repair_finalize"] = {
            "callback_url": callback_url,
            "mailbox_ref": mailbox_ref,
            "mode": str(state.get("mode") or ""),
            "runner": str(state.get("runner") or ""),
            "native_callback_state": native_callback_state,
            "stage1": stage1_state,
            "stage2": stage2_state,
            "current_url": _session_current_url(session),
        }
        session.state["repair_result"] = {
            "email": result.email,
            "auth": result.auth,
            "mode": str(state.get("mode") or ""),
            "runner": str(state.get("runner") or ""),
        }
        _record_session_event(
            session,
            "repair-finalize-complete",
            email=result.email,
            mode=str(state.get("mode") or "") or None,
            runner=str(state.get("runner") or "") or None,
            current_url=_session_current_url(session),
        )
        return result


def run_session_repair_full(
    session: BrowserSession,
    *,
    auth_obj: dict[str, Any],
    captcha_provider: str | None = None,
    browser_backend: str | None = None,
) -> runner.BrowserRegistrationResult:
    with session.lock:
        for key in ("repair_login", "repair_finalize", "repair_result", "repair_full"):
            session.state.pop(key, None)
        run_session_repair_login(
            session,
            auth_obj=auth_obj,
            captcha_provider=captcha_provider,
            browser_backend=browser_backend,
        )
        result = run_session_repair_finalize(session)
        repair_result = session.state.get("repair_result")
        session.state["repair_full"] = {
            "email": result.email,
            "mode": str((repair_result or {}).get("mode") or ""),
            "runner": str((repair_result or {}).get("runner") or ""),
            "current_url": _session_current_url(session),
        }
        _record_session_event(
            session,
            "repair-full-complete",
            email=result.email,
            mode=str((repair_result or {}).get("mode") or "") or None,
            runner=str((repair_result or {}).get("runner") or "") or None,
            current_url=_session_current_url(session),
        )
        return result
