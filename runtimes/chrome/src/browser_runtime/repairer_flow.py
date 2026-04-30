from __future__ import annotations

import os
import re
import time
from typing import Any, Callable

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from .camoufox_native import (
    auth_surface_has_challenge,
    auth_surface_stage,
    inspect_auth_surface_on_driver,
    inspect_callback_state_on_driver,
    run_native_repair_login_flow,
    try_native_click_consent_continue,
    try_native_auth_fill_email,
    try_native_auth_fill_password,
    try_native_submit_code,
    wait_native_callback_with_consent,
    wait_native_code_or_callback,
)
from .turnstile_runtime import maybe_solve_turnstile_challenge


def _noop_dump_page_body(*, driver, kind: str, message: str = "") -> None:
    """Fallback no-op when no dump_page_body callback provided."""
    pass


def _find_visible(driver, by, value):
    try:
        els = driver.find_elements(by, value)
    except Exception:
        return None
    for el in els:
        try:
            if el.is_displayed() and el.is_enabled():
                return el
        except Exception:
            continue
    return None


def _click_if_found(driver, xpath: str, *, click_with_debug: Callable[..., Any]) -> bool:
    try:
        el = _find_visible(driver, By.XPATH, xpath)
        if not el:
            return False
        click_with_debug(driver, el, tag="click_if_found", note=f"xpath={xpath[:120]}")
        return True
    except Exception:
        return False


def _wait_for_any(driver, *, timeout_seconds: int, predicates: list[Callable[[], Any]]) -> Any:
    end = time.time() + timeout_seconds
    last_exc: Exception | None = None
    while time.time() < end:
        for p in predicates:
            try:
                v = p()
                if v:
                    return v
            except Exception as e:
                last_exc = e
        time.sleep(0.4)
    raise RuntimeError(f"timeout waiting for condition: {last_exc}")


def _normalize_auth_error_code(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9_]+", "_", str(value or "").strip().lower()).strip("_")
    return normalized


def _extract_explicit_auth_error_code(*parts: str) -> str | None:
    joined = "\n".join(str(part or "") for part in parts)
    match = re.search(r"an error occurred during authentication\s*\(([^)]+)\)", joined, flags=re.IGNORECASE)
    if not match:
        return None
    normalized = _normalize_auth_error_code(match.group(1))
    return normalized or None


def _email_verification_terminal_error(driver) -> str | None:
    try:
        txt = str(
            driver.execute_script("return document && document.body ? (document.body.innerText || '') : ''; ")
            or ""
        ).lower()
    except Exception:
        txt = ""

    if "incorrect code" in txt or "invalid code" in txt or "wrong code" in txt or "code incorrect" in txt:
        return "Blocked: Email verification rejected with incorrect code."
    if "max_check_attempts" in txt or "an error occurred during authentication (max_check_attempts)" in txt:
        return "Blocked: Email verification rejected with max_check_attempts."
    return None


def _wait_code_try_candidates(
    *,
    candidates: list[str],
    min_mail_id_by_ref: dict[str, int],
    timeout_seconds: int,
    wait_openai_code_by_provider: Callable[..., Any],
    mailcreate_base_url: str,
    mailcreate_custom_auth: str,
    gptmail_base_url: str,
    gptmail_api_key: str,
    gptmail_keys_file: str,
    mailtm_api_base: str,
) -> tuple[str, str]:
    """Try multiple encoded mailbox_ref until we can fetch a 6-digit code.

    Special policy:
    - If GPTMail is quota-limited (or all keys exhausted), we should NOT mark the
      auth as "unrepairable". Caller can treat it as a transient "no_quota" case.
    """

    last_err: Exception | None = None
    last_err_str = ""

    for ref in candidates:
        r = str(ref or "").strip()
        if not r:
            continue
        try:
            code = wait_openai_code_by_provider(
                provider="auto",
                mailbox_ref=r,
                mailcreate_base_url=mailcreate_base_url,
                mailcreate_custom_auth=mailcreate_custom_auth,
                gptmail_base_url=gptmail_base_url,
                gptmail_api_key=gptmail_api_key,
                gptmail_keys_file=gptmail_keys_file,
                mailtm_api_base=mailtm_api_base,
                timeout_seconds=timeout_seconds,
                min_mail_id=max(0, int(min_mail_id_by_ref.get(r, 0) or 0)),
            )
            return str(code), r
        except Exception as e:
            last_err = e
            last_err_str = str(e)

            s = last_err_str.lower()
            if "all gptmail keys are exhausted" in s or "quota" in s or "daily quota" in s:
                raise RuntimeError("no_quota_for_otp")

            if "timeout waiting for 6-digit code" in s:
                raise RuntimeError("otp_timeout")

            continue

    raise RuntimeError(f"failed to fetch openai code from all mailbox_ref candidates: {last_err}")


def repairer_drive_login_and_get_callback_url(
    *,
    driver,
    oauth: Any,
    email: str,
    password: str,
    mailbox_ref_candidates: list[str],
    smart_wait: Callable[..., Any],
    click_with_debug: Callable[..., Any],
    get_mailbox_latest_message_id_by_provider: Callable[..., Any],
    wait_openai_code_by_provider: Callable[..., Any],
    mailcreate_base_url: str,
    mailcreate_custom_auth: str,
    gptmail_base_url: str,
    gptmail_api_key: str,
    gptmail_keys_file: str,
    mailtm_api_base: str,
    dump_page_body: Callable[..., Any] | None = None,
    captcha_provider: str | None = None,
    browser_backend: str | None = None,
) -> tuple[str, str]:
    """Drive OpenAI login flow until OAuth redirects to callback URL.

    Returns:
      (callback_url, chosen_mailbox_ref)
    """

    _dump = dump_page_body or _noop_dump_page_body

    def _try_solve_challenge(reason: str) -> bool:
        return maybe_solve_turnstile_challenge(
            driver,
            provider_kind=captcha_provider,
            browser_backend=browser_backend,
            proxy=None,
            dbg_fn=lambda stage, message, **kwargs: print(
                f"[python-browser-service][repairer][{stage}] {reason}: {message}",
                flush=True,
            ),
        )

    def _is_human_verify_page() -> bool:
        if str(browser_backend or "").strip().lower() == "camoufox":
            native_surface = inspect_auth_surface_on_driver(driver)
            if auth_surface_has_challenge(native_surface) and auth_surface_stage(native_surface) not in ("email", "password", "code"):
                return True
        try:
            txt = str(
                driver.execute_script("return document && document.body ? (document.body.innerText || '') : ''; ")
                or ""
            ).lower()
        except Exception:
            txt = ""
        try:
            current_url = str(getattr(driver, "current_url", "") or "").lower()
        except Exception:
            current_url = ""
        return (
            "verify you are human" in txt
            or "performing security verification" in txt
            or "just a moment" in txt
            or "cdn-cgi/challenge-platform" in current_url
            or "/challenge" in current_url
            or "turnstile" in txt
        )

    def _is_password_stage_page() -> bool:
        if str(browser_backend or "").strip().lower() == "camoufox":
            native_surface = inspect_auth_surface_on_driver(driver)
            if auth_surface_stage(native_surface) == "password":
                return True
        try:
            found = driver.execute_script(
                """
                const sels = [
                  'input[type="password"]',
                  'input[name*="password"]',
                  'input[id*="password"]',
                  'input[autocomplete="new-password"]',
                  'input[autocomplete="current-password"]',
                  'input[aria-label*="password" i]'
                ];
                for (const s of sels) {
                  const el = document.querySelector(s);
                  if (!el) continue;
                  const st = window.getComputedStyle(el);
                  const visible = st && st.display !== 'none' && st.visibility !== 'hidden' && el.offsetParent !== null;
                  if (visible && !el.disabled) return true;
                }
                return false;
                """
            )
            if bool(found):
                return True
        except Exception:
            pass

        try:
            body_text = str(
                driver.execute_script(
                    "return (document && document.body && document.body.innerText) ? document.body.innerText : '';"
                )
                or ""
            )
            body_lower = body_text.lower()
            return (
                "创建密码" in body_text
                or "password" in body_lower
                or "new password" in body_lower
            )
        except Exception:
            return False

    def _is_unified_auth_context() -> bool:
        try:
            cur_url = str(getattr(driver, "current_url", "") or "").lower()
        except Exception:
            cur_url = ""
        return (
            "auth.openai.com/log-in-or-create-account" in cur_url
            or "auth.openai.com/api/accounts/authorize" in cur_url
            or "auth.openai.com/log-in" in cur_url
        )

    def _capture_auth_surface_snapshot() -> dict[str, Any] | None:
        try:
            return driver.execute_script(
                """
                return (function(){
                  const visible = (el) => {
                    if (!el) return false;
                    const st = window.getComputedStyle(el);
                    return !!(st && st.display !== 'none' && st.visibility !== 'hidden' && el.offsetParent !== null);
                  };
                  const textOf = (el) => ((el.innerText || el.textContent || '').trim());
                  const inputs = Array.from(document.querySelectorAll('input'))
                    .filter(visible)
                    .slice(0, 8)
                    .map((el) => ({
                      type: String(el.getAttribute('type') || ''),
                      name: String(el.getAttribute('name') || ''),
                      id: String(el.getAttribute('id') || ''),
                      autocomplete: String(el.getAttribute('autocomplete') || ''),
                      placeholder: String(el.getAttribute('placeholder') || ''),
                      value: String(el.value || ''),
                    }));
                  const buttons = Array.from(document.querySelectorAll('button,[role="button"],a'))
                    .filter(visible)
                    .slice(0, 10)
                    .map((el) => ({
                      tag: String(el.tagName || '').toLowerCase(),
                      type: String(el.getAttribute('type') || ''),
                      name: String(el.getAttribute('name') || ''),
                      value: String(el.getAttribute('value') || ''),
                      text: textOf(el).slice(0, 120),
                    }));
                  return {
                    url: String(location.href || ''),
                    title: String(document.title || ''),
                    body: String((document.body && document.body.innerText) || '').slice(0, 1000),
                    inputs,
                    buttons,
                  };
                })();
                """
            )
        except Exception:
            return None

    def _is_blank_auth_shell(snapshot: dict[str, Any] | None) -> bool:
        if not isinstance(snapshot, dict):
            return False
        url = str(snapshot.get("url") or "").lower()
        title = str(snapshot.get("title") or "").strip()
        body = str(snapshot.get("body") or "").strip()
        inputs = snapshot.get("inputs")
        buttons = snapshot.get("buttons")
        return (
            "auth.openai.com" in url
            and "log-in" in url
            and not title
            and not body
            and isinstance(inputs, list)
            and isinstance(buttons, list)
            and len(inputs) == 0
            and len(buttons) == 0
        )

    def _resubmit_unified_email_stage(email_value: str) -> dict[str, Any] | None:
        try:
            return driver.execute_script(
                """
                return (function(expectedEmail){
                  const visible = (el) => {
                    if (!el) return false;
                    const st = window.getComputedStyle(el);
                    return !!(st && st.display !== 'none' && st.visibility !== 'hidden' && el.offsetParent !== null);
                  };
                  const textOf = (el) => ((el.innerText || el.textContent || '').trim());
                  const emailSelectors = [
                    'input[type="email"]',
                    'input[name*="email"]',
                    'input[id*="email"]',
                    'input[autocomplete="email"]',
                    'input[autocomplete="username"]',
                    'input[placeholder*="email" i]'
                  ];
                  let emailInput = null;
                  for (const sel of emailSelectors) {
                    const el = document.querySelector(sel);
                    if (visible(el) && !el.disabled) {
                      emailInput = el;
                      break;
                    }
                  }
                  let emailValue = '';
                  let emailPresent = !!emailInput;
                  let action = 'none';
                  let buttonText = '';
                  if (emailInput) {
                    try {
                      const proto = (emailInput.tagName || '').toLowerCase() === 'textarea'
                        ? window.HTMLTextAreaElement.prototype
                        : window.HTMLInputElement.prototype;
                      const nativeSetter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
                      if ((emailInput.value || '') !== expectedEmail) {
                        if (typeof nativeSetter === 'function') {
                          nativeSetter.call(emailInput, expectedEmail);
                        } else {
                          emailInput.value = expectedEmail;
                        }
                      }
                      emailInput.dispatchEvent(new Event('input', { bubbles: true }));
                      emailInput.dispatchEvent(new Event('change', { bubbles: true }));
                      try { emailInput.dispatchEvent(new FocusEvent('blur', { bubbles: true })); } catch (e) {}
                      try { emailInput.blur(); } catch (e) {}
                      emailValue = String(emailInput.value || '');
                    } catch (e) {}
                  }

                  const candidateSelectors = [
                    'button[type="submit"][name="intent"][value="email"]',
                    'button[name="intent"][value="email"]',
                    'button[type="submit"]:not([disabled])',
                    'button:not([disabled])',
                    '[role="button"]'
                  ];
                  let btn = null;
                  for (const sel of candidateSelectors) {
                    const nodes = Array.from(document.querySelectorAll(sel));
                    for (const node of nodes) {
                      if (!visible(node)) continue;
                      const txt = textOf(node);
                      if (!txt) continue;
                      if (!/continue|log in|sign in|next|password/i.test(txt)) continue;
                      btn = node;
                      buttonText = txt.slice(0, 120);
                      break;
                    }
                    if (btn) break;
                  }

                  if (btn) {
                    try {
                      btn.click();
                      action = 'click_button';
                    } catch (e) {}
                  }

                  if (action === 'none' && emailInput) {
                    try {
                      const form = emailInput.closest('form');
                      if (form && typeof form.requestSubmit === 'function') {
                        form.requestSubmit();
                        action = 'request_submit';
                      } else if (form) {
                        form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
                        form.submit();
                        action = 'form_submit';
                      }
                    } catch (e) {}
                  }

                  if (action === 'none' && emailInput) {
                    try {
                      emailInput.focus();
                      emailInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true }));
                      emailInput.dispatchEvent(new KeyboardEvent('keypress', { key: 'Enter', code: 'Enter', bubbles: true }));
                      emailInput.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', bubbles: true }));
                      action = 'dispatch_enter';
                    } catch (e) {}
                  }

                  return {
                    ok: true,
                    emailPresent,
                    emailValue,
                    action,
                    buttonText,
                    url: String(location.href || ''),
                    body: String((document.body && document.body.innerText) || '').slice(0, 1000),
                  };
                })(arguments[0]);
                """,
                email_value,
            )
        except Exception:
            return None

    def _try_locate_email_input_once() -> Any:
        try:
            candidate = driver.execute_script(
                """
                const sels = [
                  'input[type="email"]',
                  'input[name="email"]',
                  'input[name*="email"]',
                  'input[id$="-email"]',
                  'input[id*="-email"]',
                  'input[id*="email"]',
                  'input[autocomplete="email"]',
                  'input[autocomplete="username"]',
                  'input[placeholder*="email" i]'
                ];
                for (const s of sels) {
                  const el = document.querySelector(s);
                  if (!el) continue;
                  const st = window.getComputedStyle(el);
                  const visible = st && st.display !== 'none' && st.visibility !== 'hidden' && el.offsetParent !== null;
                  if (visible && !el.disabled) return el;
                }
                return null;
                """
            )
            if candidate is not None:
                return candidate
        except Exception:
            pass
        for sel in email_selectors:
            candidate = _find_visible(driver, By.CSS_SELECTOR, sel)
            if candidate:
                return candidate
        return None

    def _inspect_auth_surface_state() -> dict[str, Any]:
        native_surface = inspect_auth_surface_on_driver(driver)
        snapshot = _capture_auth_surface_snapshot()
        ready_state = ""
        try:
            ready_state = str(driver.execute_script("return document.readyState || ''; ") or "")
        except Exception:
            ready_state = ""
        has_snapshot_content = False
        if isinstance(snapshot, dict):
            has_snapshot_content = bool(
                str(snapshot.get("title") or "").strip()
                or str(snapshot.get("body") or "").strip()
                or list(snapshot.get("inputs") or [])
                or list(snapshot.get("buttons") or [])
            )
        return {
            "nativeSurface": native_surface,
            "nativeStage": auth_surface_stage(native_surface),
            "snapshot": snapshot,
            "snapshotBlank": _is_blank_auth_shell(snapshot),
            "snapshotHasContent": has_snapshot_content,
            "readyState": ready_state,
        }

    def _wait_for_auth_surface_recovery(*, reason: str, timeout_seconds: float) -> str | None:
        deadline = time.time() + max(3.0, float(timeout_seconds))
        last_state: dict[str, Any] | None = None
        last_hydrating_log_at = 0.0
        while time.time() < deadline:
            if _is_password_stage_page():
                return "password"
            if _try_locate_email_input_once() is not None:
                return "email"

            state = _inspect_auth_surface_state()
            last_state = state
            native_stage = str(state.get("nativeStage") or "")
            if native_stage in ("password", "email", "code"):
                return native_stage

            if native_stage == "challenge":
                if _try_solve_challenge(f"{reason}-challenge"):
                    time.sleep(1.5)
                    continue

            if state.get("snapshotHasContent"):
                now = time.time()
                if now - last_hydrating_log_at >= 3.0:
                    print(
                        "[python-browser-service][repairer] auth surface hydrating "
                        f"reason={reason} state={state}",
                        flush=True,
                    )
                    last_hydrating_log_at = now
                if _is_unified_auth_context():
                    result = _resubmit_unified_email_stage(email)
                    if result is not None and result.get("action") not in ("", "none"):
                        print(
                            "[python-browser-service][repairer] auth surface nudge "
                            f"reason={reason} result={result}",
                            flush=True,
                        )
                time.sleep(0.75)
                continue

            if _try_solve_challenge(f"{reason}-wait"):
                time.sleep(1.5)
                continue
            time.sleep(0.75)

        print(
            "[python-browser-service][repairer] auth surface recovery timeout "
            f"reason={reason} state={last_state}",
            flush=True,
        )
        return None

    def _recover_blank_auth_shell(*, oauth_url: str) -> bool:
        recovered_stage = _wait_for_auth_surface_recovery(reason="blank-auth-shell-precheck", timeout_seconds=6.0)
        if recovered_stage in ("password", "email", "code"):
            _dump(driver=driver, kind="repair_blank_auth_shell_recovered", message=f"precheck:{recovered_stage}")
            return True

        recovery_steps = [
            ("refresh", lambda: driver.refresh()),
            ("reload_oauth", lambda: driver.get(oauth_url)),
            ("replace_oauth", lambda: driver.execute_script("window.location.replace(arguments[0]);", oauth_url)),
        ]
        for label, action in recovery_steps:
            if label != "refresh" and not str(oauth_url or "").strip():
                continue
            try:
                print(f"[python-browser-service][repairer] attempting blank-shell recovery step={label}", flush=True)
                action()
            except Exception as exc:
                print(f"[python-browser-service][repairer] blank-shell recovery step={label} failed: {exc}", flush=True)
                continue

            try:
                WebDriverWait(driver, 30).until(EC.url_contains("auth.openai.com"))
            except Exception:
                pass

            recovered_stage = _wait_for_auth_surface_recovery(reason=label, timeout_seconds=10.0)
            if recovered_stage in ("password", "email", "code"):
                _dump(
                    driver=driver,
                    kind="repair_blank_auth_shell_recovered",
                    message=f"{label}:{recovered_stage}",
                )
                return True

            snapshot = _inspect_auth_surface_state()
            print(
                "[python-browser-service][repairer] blank-shell recovery result "
                f"step={label} snapshot={snapshot}",
                flush=True,
            )
        return False

    otp_min_mail_id_by_ref: dict[str, int] = {}
    for ref in mailbox_ref_candidates:
        candidate = str(ref or "").strip()
        if not candidate:
            continue
        try:
            otp_min_mail_id_by_ref[candidate] = int(
                get_mailbox_latest_message_id_by_provider(
                    mailbox_ref=candidate,
                    mailcreate_base_url=mailcreate_base_url,
                    mailcreate_custom_auth=mailcreate_custom_auth,
                )
                or 0
            )
        except Exception as exc:
            print(
                "[python-browser-service] OTP baseline lookup skipped "
                f"ref_prefix={candidate[:40]} err={exc}"
            )

    def _refresh_mailbox_baseline() -> None:
        for ref in mailbox_ref_candidates:
            candidate = str(ref or "").strip()
            if not candidate:
                continue
            try:
                latest_id = int(
                    get_mailbox_latest_message_id_by_provider(
                        mailbox_ref=candidate,
                        mailcreate_base_url=mailcreate_base_url,
                        mailcreate_custom_auth=mailcreate_custom_auth,
                    )
                    or 0
                )
            except Exception:
                continue
            otp_min_mail_id_by_ref[candidate] = max(
                latest_id,
                int(otp_min_mail_id_by_ref.get(candidate, 0) or 0),
            )

    driver.get(oauth.auth_url)

    try:
        WebDriverWait(driver, 60).until(EC.url_contains("auth.openai.com"))
    except Exception:
        raise RuntimeError("did not reach auth.openai.com")

    if str(browser_backend or "").strip().lower() == "camoufox":
        def _fetch_code_native() -> tuple[str, str]:
            print(
                "[python-browser-service] native repair flow waiting for OTP "
                f"candidate_count={len(mailbox_ref_candidates)}"
            )
            return _wait_code_try_candidates(
                candidates=mailbox_ref_candidates,
                min_mail_id_by_ref=otp_min_mail_id_by_ref,
                timeout_seconds=180,
                wait_openai_code_by_provider=wait_openai_code_by_provider,
                mailcreate_base_url=mailcreate_base_url,
                mailcreate_custom_auth=mailcreate_custom_auth,
                gptmail_base_url=gptmail_base_url,
                gptmail_api_key=gptmail_api_key,
                gptmail_keys_file=gptmail_keys_file,
                mailtm_api_base=mailtm_api_base,
            )

        try:
            native_result = run_native_repair_login_flow(
                driver,
                email=email,
                password=password,
                fetch_code_fn=_fetch_code_native,
                try_solve_challenge_fn=_try_solve_challenge,
                callback_url_contains="localhost:1455",
            )
            callback_url = str(native_result.get("callback_url") or "")
            chosen_ref = str(native_result.get("chosen_mailbox_ref") or "")
            if callback_url:
                try:
                    setattr(driver, "_neuro_repair_flow_result", native_result)
                except Exception:
                    pass
                try:
                    setattr(driver, "_neuro_finalize_callback_state", {
                        "url": callback_url,
                        "callbackMatched": True,
                        "onConsentPage": False,
                        "challengePresent": False,
                    })
                except Exception:
                    pass
                _dump(driver=driver, kind="native_repair_flow_success", message=f"mode={native_result.get('mode')}")
                return callback_url, chosen_ref
        except Exception as exc:
            print(f"[python-browser-service][repairer] native repair flow fallback: {exc}", flush=True)
            _dump(driver=driver, kind="native_repair_flow_fallback", message=str(exc))
            driver.get(oauth.auth_url)
            try:
                WebDriverWait(driver, 60).until(EC.url_contains("auth.openai.com"))
            except Exception:
                raise RuntimeError("native repair flow fallback failed to return to auth.openai.com")

    debug_visible = int(os.environ.get("HEADLESS", "1") or "1") == 0
    email_wait_rounds = int(
        os.environ.get(
            "DEBUG_REPAIR_EMAIL_WAIT_ROUNDS",
            "3" if debug_visible else "2",
        )
        or ("3" if debug_visible else "2")
    )
    if email_wait_rounds < 1:
        email_wait_rounds = 1

    email_input = None
    last_email_err: Exception | None = None
    skip_email_submit = False
    email_selectors = [
        'input[type="email"]',
        'input[name="email"]',
        'input[name*="email"]',
        'input[id$="-email"]',
        'input[id*="-email"]',
        'input[id*="email"]',
        'input[autocomplete="email"]',
        'input[autocomplete="username"]',
        'input[placeholder*="email" i]',
    ]
    for _round in range(1, email_wait_rounds + 1):
        if _is_password_stage_page():
            skip_email_submit = True
            break
        if _is_human_verify_page():
            if _try_solve_challenge("before-email"):
                time.sleep(1.0)
                continue
        email_input = _try_locate_email_input_once()
        if email_input is not None:
            break

        try:
            email_input = smart_wait(
                driver,
                By.CSS_SELECTOR,
                ", ".join(email_selectors),
                timeout=35 if debug_visible else 20,
                debug_kind="repair_email_input",
                debug_message="repair email input not found",
            )
            break
        except Exception as exc:
            last_email_err = exc

        if _round == 1 or _round == email_wait_rounds:
            snapshot = _capture_auth_surface_snapshot()
            if snapshot is not None:
                print(
                    "[python-browser-service][repairer] email-stage snapshot "
                    f"round={_round}/{email_wait_rounds} snapshot={snapshot}",
                    flush=True,
                )
                _dump(
                    driver=driver,
                    kind="repair_email_stage_snapshot",
                    message=f"round={_round}/{email_wait_rounds}",
                )
        if _round < email_wait_rounds:
            time.sleep(float(os.environ.get("DEBUG_REPAIR_EMAIL_RETRY_SLEEP_SECONDS", "2.0") or "2.0"))

    if not skip_email_submit and not email_input:
        snapshot = _capture_auth_surface_snapshot()
        recovered_from_blank_shell = False
        if _is_blank_auth_shell(snapshot):
            print(
                "[python-browser-service][repairer] blank auth shell detected during repair email stage",
                flush=True,
            )
            _dump(driver=driver, kind="repair_blank_auth_shell", message="blank auth shell before email input")
            if not _recover_blank_auth_shell(oauth_url=str(getattr(oauth, "auth_url", "") or "")):
                raise RuntimeError("blocked challenge page")
            recovered_from_blank_shell = True
            if _is_password_stage_page():
                skip_email_submit = True
            else:
                email_input = _try_locate_email_input_once()
                if email_input is None:
                    raise RuntimeError("blocked challenge page")
        if email_input is None and not skip_email_submit:
            if last_email_err is not None:
                print(f"[python-browser-service][repairer] email-stage last error: {last_email_err}", flush=True)
            message = "email input not found after retries"
            if recovered_from_blank_shell:
                message = "email input not found after blank-shell recovery"
            _dump(driver=driver, kind="repair_email_input_missing", message=message)
            raise RuntimeError(message)

    native_email_submitted = False
    if str(browser_backend or "").strip().lower() == "camoufox":
        native_email_result = try_native_auth_fill_email(driver, str(email), submit=True)
        if isinstance(native_email_result, dict) and native_email_result.get("ok"):
            print(f"[python-browser-service][repairer] native email primitive result={native_email_result}", flush=True)
            if str(native_email_result.get("emailValue") or "") == str(email) and str(native_email_result.get("action") or "") not in ("", "filled"):
                native_email_submitted = True

    if not skip_email_submit and not native_email_submitted:
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", email_input)
        except Exception:
            pass
        js_ok = False
        try:
            email_input.click()
        except Exception:
            try:
                driver.execute_script("arguments[0].focus();", email_input)
            except Exception:
                pass
        try:
            email_input.clear()
        except Exception:
            pass
        try:
            driver.execute_script(
                """
                const el = arguments[0];
                const v = arguments[1];
                if (!el) return false;
                el.focus();
                const proto = (el.tagName || '').toLowerCase() === 'textarea'
                  ? window.HTMLTextAreaElement.prototype
                  : window.HTMLInputElement.prototype;
                const nativeSetter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
                if (typeof nativeSetter === 'function') {
                    nativeSetter.call(el, v);
                } else {
                    el.value = v;
                }
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                try { el.dispatchEvent(new FocusEvent('blur', { bubbles: true })); } catch (e) {}
                try { el.blur(); } catch (e) {}
                return (el.value || '') === v;
                """,
                email_input,
                str(email),
            )
            js_ok = str(email_input.get_attribute("value") or "") == str(email)
        except Exception:
            js_ok = False
        if not js_ok:
            email_input.send_keys(str(email))
        final_email_value = ""
        try:
            final_email_value = str(email_input.get_attribute("value") or "")
        except Exception:
            final_email_value = ""
        if final_email_value != str(email):
            _dump(driver=driver, kind="repair_email_fill_mismatch", message=f"got={final_email_value!r}")
            raise RuntimeError(f"repair email not filled as expected: got={final_email_value!r} want={email!r}")

        continue_btn = None
        try:
            continue_btn = driver.execute_script(
                """
                const selectors = [
                  'button[type="submit"][name="intent"][value="email"]',
                  'button[name="intent"][value="email"]',
                  'button[type="submit"]:not([disabled])',
                  'button:not([disabled])',
                  '[role="button"][data-action*="continue" i]',
                  '[role="button"][aria-label*="continue" i]'
                ];
                for (const s of selectors) {
                  const nodes = Array.from(document.querySelectorAll(s));
                  for (const n of nodes) {
                    const t = (n.innerText || n.textContent || '').trim();
                    const st = window.getComputedStyle(n);
                    const visible = st && st.display !== 'none' && st.visibility !== 'hidden' && n.offsetParent !== null;
                    const disabled = !!(n.disabled || n.getAttribute('aria-disabled') === 'true');
                    if (!visible || disabled) continue;
                    if (!t || !/continue|log in|sign in|next|password/i.test(t)) continue;
                    return n;
                  }
                }
                return null;
                """
            )
        except Exception:
            continue_btn = None
        if continue_btn is not None:
            click_with_debug(driver, continue_btn, tag="repair_email_continue", note="submit repair email step")
        else:
            try:
                email_input.send_keys(Keys.ENTER)
            except Exception:
                pass
        _dump(driver=driver, kind="email_submitted", message="email submitted")
    elif skip_email_submit:
        _dump(driver=driver, kind="repair_email_skipped", message="password stage already present")
    else:
        _dump(driver=driver, kind="email_submitted_native", message="email submitted via native camoufox primitive")

    unified_followup_rounds = int(
        os.environ.get(
            "DEBUG_REPAIR_UNIFIED_FOLLOWUP_ROUNDS",
            "4" if debug_visible else "2",
        )
        or ("4" if debug_visible else "2")
    )
    if unified_followup_rounds < 1:
        unified_followup_rounds = 1
    for _round in range(1, unified_followup_rounds + 1):
        if _is_password_stage_page():
            break
        if _is_human_verify_page():
            if _try_solve_challenge("after-email"):
                time.sleep(1.0)
                continue
        if _is_unified_auth_context():
            result = _resubmit_unified_email_stage(str(email))
            if result is not None:
                print(
                    "[python-browser-service][repairer] unified email followup "
                    f"round={_round}/{unified_followup_rounds} result={result}",
                    flush=True,
                )
        if _round < unified_followup_rounds:
            time.sleep(float(os.environ.get("DEBUG_REPAIR_PASSWORD_RETRY_SLEEP_SECONDS", "2.0") or "2.0"))

    def _password_input():
        selectors = [
            'input[type="password"]',
            'input[name*="password" i]',
            'input[id*="password" i]',
            'input[autocomplete="current-password"]',
            'input[autocomplete="new-password"]',
        ]
        for sel in selectors:
            el = _find_visible(driver, By.CSS_SELECTOR, sel)
            if el:
                return el
        return None

    def _click_password_continue_if_needed() -> bool:
        try:
            button = driver.execute_script(
                """
                const visible = (el) => {
                  if (!el) return false;
                  const st = window.getComputedStyle(el);
                  return !!(st && st.display !== 'none' && st.visibility !== 'hidden' && el.offsetParent !== null);
                };
                const textOf = (el) => ((el.innerText || el.textContent || '').trim());
                const selectors = [
                  'button[type="submit"]:not([disabled])',
                  'button[name="intent"][value="password"]:not([disabled])',
                  '[role="button"]'
                ];
                for (const sel of selectors) {
                  for (const node of document.querySelectorAll(sel)) {
                    if (!visible(node)) continue;
                    const txt = textOf(node);
                    if (!txt) continue;
                    if (/one-time code/i.test(txt)) continue;
                    if (!/continue|log in|login|sign in|next|password/i.test(txt)) continue;
                    return node;
                  }
                }
                return null;
                """
            )
        except Exception:
            button = None

        if button is None:
            return False
        try:
            click_with_debug(driver, button, tag="repair_password_continue", note="submit repair password step")
            _dump(driver=driver, kind="password_continue_clicked", message="password continue clicked")
            return True
        except Exception:
            return False

    for _ in range(60):
        if _is_human_verify_page():
            if _try_solve_challenge("before-password"):
                time.sleep(1.0)
                continue
        pwd_inp = _password_input()
        if pwd_inp:
            native_password_submitted = False
            if str(browser_backend or "").strip().lower() == "camoufox":
                native_password_result = try_native_auth_fill_password(driver, str(password), submit=True)
                if isinstance(native_password_result, dict) and native_password_result.get("ok"):
                    print(f"[python-browser-service][repairer] native password primitive result={native_password_result}", flush=True)
                    if native_password_result.get("passwordFilled") and str(native_password_result.get("action") or "") not in ("", "filled"):
                        native_password_submitted = True
            if not native_password_submitted:
                try:
                    pwd_inp.clear()
                except Exception:
                    pass
                pwd_inp.send_keys(str(password))
                if not _click_password_continue_if_needed():
                    pwd_inp.send_keys(Keys.ENTER)
                _dump(driver=driver, kind="password_submitted", message="password submitted")
            else:
                _dump(driver=driver, kind="password_submitted_native", message="password submitted via native camoufox primitive")
            break

        if _click_if_found(
            driver,
            "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'continue with password') or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'password')]",
            click_with_debug=click_with_debug,
        ):
            time.sleep(0.6)
            continue

        _click_if_found(
            driver,
            "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'continue')]",
            click_with_debug=click_with_debug,
        )
        time.sleep(0.6)

    otp_stage_ready = False
    otp_stage_reason = ""
    otp_wait_timeout = int(os.environ.get("REPAIR_OTP_STAGE_WAIT_SECONDS", "45") or "45")
    if otp_wait_timeout < 20:
        otp_wait_timeout = 20
    end_ts = time.time() + otp_wait_timeout
    while time.time() < end_ts:
        try:
            cur_url = str(getattr(driver, "current_url", "") or "")
        except Exception:
            cur_url = ""
        try:
            page_txt = str(driver.execute_script("return document && document.body ? (document.body.innerText || '') : ''; ") or "")
        except Exception:
            page_txt = ""

        if "localhost:1455" in cur_url:
            otp_stage_ready = True
            otp_stage_reason = "callback"
            break
        if "email-verification" in cur_url:
            otp_stage_ready = True
            otp_stage_reason = "url=email-verification"
            break
        if str(browser_backend or "").strip().lower() == "camoufox":
            native_surface = inspect_auth_surface_on_driver(driver)
            native_stage = auth_surface_stage(native_surface)
            if native_stage == "code":
                otp_stage_ready = True
                otp_stage_reason = "native_code_surface"
                break
            if isinstance(inspect_callback_state_on_driver(driver, callback_url_contains="localhost:1455"), dict):
                callback_state = inspect_callback_state_on_driver(driver, callback_url_contains="localhost:1455")
                if callback_state.get("callbackMatched"):
                    otp_stage_ready = True
                    otp_stage_reason = "native_callback"
                    break

        lower_txt = page_txt.lower()
        on_password_page = (
            "log-in/password" in cur_url.lower()
            or "enter your password" in lower_txt
        )
        if not on_password_page and (
            "verification code" in lower_txt
            or "check your inbox" in lower_txt
            or "resend email" in lower_txt
            or "enter code" in lower_txt
            or "email a code" in lower_txt
        ):
            otp_stage_ready = True
            otp_stage_reason = "page_text_hint"
            break
        try:
            els = driver.find_elements(
                By.CSS_SELECTOR,
                'input[autocomplete="one-time-code"], input[inputmode="numeric"][maxlength="6"], div[role="group"] input[inputmode="numeric"][maxlength="1"]',
            )
            if els:
                otp_stage_ready = True
                otp_stage_reason = "otp_input_found"
                break
        except Exception:
            pass
        if on_password_page:
            _click_password_continue_if_needed()
        if _is_human_verify_page():
            if _try_solve_challenge("post-password"):
                time.sleep(1.0)
                continue
        time.sleep(0.4)

    if not otp_stage_ready:
        _dump(driver=driver, kind="repair_otp_stage_ready", message="password submitted but otp stage not reached")
        raise RuntimeError("password submitted but otp stage not reached")

    def _has_callback() -> bool:
        try:
            return "localhost:1455" in str(getattr(driver, "current_url", "") or "")
        except Exception:
            return False

    def _code_input():
        selectors = [
            'input[id*="code"]',
            'input[name*="code"]',
            'input[autocomplete="one-time-code"]',
            'input[inputmode="numeric"][maxlength="6"]',
            'input[aria-label*="code" i]',
            'input[placeholder*="code" i]',
        ]

        for sel in selectors:
            el = _find_visible(driver, By.CSS_SELECTOR, sel)
            if el:
                return el

        try:
            group = driver.find_elements(By.CSS_SELECTOR, 'div[role="group"] input[inputmode="numeric"][maxlength="1"]')
            if group:
                return group
        except Exception:
            pass

        return None

    def _has_risk_text_hint() -> bool:
        try:
            txt = str(driver.execute_script("return document && document.body ? (document.body.innerText || '') : ''; ") or "").lower()
        except Exception:
            txt = ""

        hints = [
            "verification code",
            "enter code",
            "check your email",
            "email a code",
            "send code",
            "verify it's you",
            "???",
            "?????",
            "?????",
            "??????",
        ]
        return any(h in txt for h in hints)

    def _click_send_code_if_needed() -> bool:
        send_code_xpaths = [
            "//*[self::button or self::a or self::span][contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'send code')]",
            "//*[self::button or self::a or self::span][contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'email me a code')]",
            "//*[self::button or self::a or self::span][contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'send verification')]",
            "//*[self::button or self::a or self::span][contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'get code')]",
            "//*[self::button or self::a or self::span][contains(., '?????') or contains(., '???') or contains(., '????')]",
            "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'continue') and not(contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'with'))]",
        ]

        for xp in send_code_xpaths:
            if _click_if_found(driver, xp, click_with_debug=click_with_debug):
                print(f"[python-browser-service] clicked OTP send action xpath={xp[:80]}")
                time.sleep(1.0)
                return True

        return False

    def _click_resend_email() -> bool:
        resend_xpaths = [
            "//*[self::button or self::a or self::span][contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'resend email')]",
            "//*[self::button or self::a or self::span][contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'resend code')]",
            "//*[self::button or self::a or self::span][contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'send again')]",
        ]
        for xp in resend_xpaths:
            if _click_if_found(driver, xp, click_with_debug=click_with_debug):
                print(f"[python-browser-service] clicked OTP resend action xpath={xp[:80]}", flush=True)
                time.sleep(1.0)
                return True
        return False

    def _has_incorrect_code_hint() -> bool:
        try:
            txt = str(
                driver.execute_script("return document && document.body ? (document.body.innerText || '') : ''; ")
                or ""
            ).lower()
        except Exception:
            txt = ""
        hints = [
            "incorrect code",
            "invalid code",
            "wrong code",
            "code incorrect",
        ]
        return any(h in txt for h in hints)

    def _click_consent_continue_if_needed() -> bool:
        try:
            current_url = str(getattr(driver, "current_url", "") or "").lower()
        except Exception:
            current_url = ""
        if "sign-in-with-chatgpt/codex/consent" not in current_url:
            return False

        consent_xpaths = [
            "//button[contains(normalize-space(.), 'Continue')]",
            "//button[contains(normalize-space(.), 'Agree')]",
            "//a[contains(normalize-space(.), 'Continue')]",
        ]
        for xp in consent_xpaths:
            if _click_if_found(driver, xp, click_with_debug=click_with_debug):
                _dump(driver=driver, kind="consent_continue_clicked", message="consent continue clicked")
                time.sleep(1.0)
                return True
        return False

    def _submit_code(target: Any, code: str, *, tag: str) -> None:
        if isinstance(target, list):
            for cur, digit in zip(target, str(code)):
                try:
                    click_with_debug(driver, cur, tag="repairer_otp_digit_box", note=f"{tag} segmented otp input")
                    cur.clear()
                except Exception:
                    pass
                cur.send_keys(str(digit))
            try:
                driver.switch_to.active_element.send_keys(Keys.ENTER)
            except Exception:
                pass
        else:
            try:
                target.clear()
            except Exception:
                pass
            target.send_keys(str(code))
            target.send_keys(Keys.ENTER)
        _dump(driver=driver, kind=tag, message=f"code submitted ({tag})")

    def _await_callback_or_code_stage() -> Any:
        if str(browser_backend or "").strip().lower() == "camoufox":
            native_callback = inspect_callback_state_on_driver(driver, callback_url_contains="localhost:1455")
            if isinstance(native_callback, dict) and native_callback.get("callbackMatched"):
                return "CALLBACK"
        if _has_callback():
            return "CALLBACK"

        if _is_human_verify_page():
            if _try_solve_challenge("wait-code-or-callback"):
                return None

        if str(browser_backend or "").strip().lower() == "camoufox":
            native_surface = inspect_auth_surface_on_driver(driver)
            if auth_surface_stage(native_surface) == "code":
                return _code_input() or "CODE_STAGE"

        ci = _code_input()
        if ci:
            return ci

        if _has_risk_text_hint():
            _click_send_code_if_needed()
            ci2 = _code_input()
            if ci2:
                return ci2

        return None

    v = "CALLBACK" if otp_stage_reason in ("callback", "native_callback") else None
    if str(browser_backend or "").strip().lower() == "camoufox":
        native_wait = wait_native_code_or_callback(
            driver,
            timeout_seconds=50,
            callback_url_contains="localhost:1455",
            try_solve_challenge_fn=_try_solve_challenge,
        )
        if native_wait.get("kind") == "callback":
            v = "CALLBACK"
        elif native_wait.get("kind") == "code":
            v = _code_input() or "CODE_STAGE"

    if v is None:
        v = _wait_for_any(driver, timeout_seconds=80, predicates=[_await_callback_or_code_stage])

    chosen_ref = ""
    post_otp_auth_error_recovery_attempted = False
    last_post_otp_auth_error_state: dict[str, str] | None = None
    post_otp_auth_error_returned_to_auth_stage = ""

    def _raise_if_terminal_otp_rejection(*, tag_suffix: str = "") -> None:
        terminal_error = _email_verification_terminal_error(driver)
        if not terminal_error:
            return
        _dump(
            driver=driver,
            kind=f"otp_terminal_rejection{tag_suffix}",
            message=terminal_error,
        )
        raise RuntimeError(terminal_error)

    def _auth_error_page_state() -> dict[str, str] | None:
        try:
            body_text = str(
                driver.execute_script(
                    "return document && document.body ? (document.body.innerText || '') : ''; "
                )
                or ""
            )
        except Exception:
            body_text = ""
        try:
            title_text = str(driver.execute_script("return (document && document.title) ? document.title : '';") or "")
        except Exception:
            title_text = ""
        try:
            current_url = str(getattr(driver, "current_url", "") or "")
        except Exception:
            current_url = ""

        joined = "\n".join([title_text, body_text, current_url]).lower()
        if not (
            "oops, an error occurred" in joined
            or "an error occurred during authentication" in joined
            or "account has been deleted or deactivated" in joined
            or "account_deactivated" in joined
            or ("oops" in joined and "try again" in joined)
        ):
            return None

        explicit_auth_error_code = _extract_explicit_auth_error_code(title_text, body_text)
        code = "auth_error_page"
        if explicit_auth_error_code:
            code = explicit_auth_error_code
        elif "account has been deleted or deactivated" in joined or "account_deactivated" in joined:
            code = "account_deactivated"
        elif "an error occurred during authentication" in joined:
            code = "auth_error_during_authentication"

        return {
            "code": code,
            "url": current_url,
            "title": title_text,
            "body": body_text[:1000],
        }

    def _click_auth_error_try_again_if_needed() -> bool:
        retry_xpaths = [
            "//*[self::button or self::a or self::div][contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'try again')]",
            "//*[self::button or self::a or self::div][contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'retry')]",
        ]
        for xp in retry_xpaths:
            if _click_if_found(driver, xp, click_with_debug=click_with_debug):
                _dump(driver=driver, kind="auth_error_try_again_clicked", message=xp[:120])
                time.sleep(1.0)
                return True
        return False

    def _is_terminal_post_otp_auth_error(state: dict[str, str] | None) -> bool:
        if not isinstance(state, dict):
            return False
        code = str(state.get("code") or "").strip().lower()
        if not code:
            return False
        return code not in {"auth_error_page", "auth_error_during_authentication"}

    def _try_recover_post_otp_auth_error(*, reason: str) -> bool:
        nonlocal post_otp_auth_error_recovery_attempted
        nonlocal last_post_otp_auth_error_state
        nonlocal post_otp_auth_error_returned_to_auth_stage
        if post_otp_auth_error_recovery_attempted:
            return False
        state = _auth_error_page_state()
        if not state:
            return False

        post_otp_auth_error_recovery_attempted = True
        last_post_otp_auth_error_state = dict(state)
        post_otp_auth_error_returned_to_auth_stage = ""
        _dump(
            driver=driver,
            kind="post_otp_auth_error_detected",
            message=f"{reason} code={state.get('code')} url={state.get('url')}",
        )

        if _click_auth_error_try_again_if_needed():
            time.sleep(1.5)
            if _has_callback():
                _dump(
                    driver=driver,
                    kind="post_otp_auth_error_recovery",
                    message=f"{reason} method=try_again_callback code={state.get('code')}",
                )
                return True
            residual_state = _auth_error_page_state()
            if residual_state is None:
                _dump(
                    driver=driver,
                    kind="post_otp_auth_error_recovery",
                    message=f"{reason} method=try_again code={state.get('code')}",
                )
                return True
            _dump(
                driver=driver,
                kind="post_otp_auth_error_retry_still_blocked",
                message=f"{reason} code={residual_state.get('code')} url={residual_state.get('url')}",
            )

        auth_url = str(getattr(oauth, "auth_url", "") or "").strip()
        if auth_url:
            try:
                driver.get(auth_url)
                restored_stage = _wait_for_auth_surface_recovery(
                    reason="post-otp-reload-oauth",
                    timeout_seconds=8.0,
                )
                if restored_stage in ("email", "password", "code"):
                    post_otp_auth_error_returned_to_auth_stage = restored_stage
                _dump(
                    driver=driver,
                    kind="post_otp_auth_error_recovery",
                    message=(
                        f"{reason} method=reload_oauth code={state.get('code')}"
                        if not post_otp_auth_error_returned_to_auth_stage
                        else (
                            f"{reason} method=reload_oauth_returned_auth "
                            f"stage={post_otp_auth_error_returned_to_auth_stage} code={state.get('code')}"
                        )
                    ),
                )
                return True
            except Exception as exc:
                _dump(
                    driver=driver,
                    kind="post_otp_auth_error_recovery_failed",
                    message=f"{reason} method=reload_oauth err={exc}",
                )
        return False

    def _wait_callback_with_consent(timeout: int = 60) -> bool:
        if str(browser_backend or "").strip().lower() == "camoufox":
            if wait_native_callback_with_consent(
                driver,
                timeout_seconds=timeout,
                callback_url_contains="localhost:1455",
                try_solve_challenge_fn=_try_solve_challenge,
            ):
                return True
        end = time.time() + max(5, int(timeout))
        while time.time() < end:
            if str(browser_backend or "").strip().lower() == "camoufox":
                native_callback = inspect_callback_state_on_driver(driver, callback_url_contains="localhost:1455")
                if isinstance(native_callback, dict):
                    if native_callback.get("callbackMatched"):
                        return True
                    if native_callback.get("onConsentPage"):
                        consent_result = try_native_click_consent_continue(driver)
                        if isinstance(consent_result, dict) and consent_result.get("ok"):
                            print(f"[python-browser-service][repairer] native consent primitive result={consent_result}", flush=True)
                            time.sleep(0.8)
                            continue
            if _has_callback():
                return True
            if _is_human_verify_page():
                if _try_solve_challenge("wait-callback"):
                    time.sleep(1.0)
                    continue
            try:
                if _click_consent_continue_if_needed():
                    time.sleep(1.0)
                    continue
            except Exception:
                pass
            current_auth_error_state = _auth_error_page_state()
            if _is_terminal_post_otp_auth_error(current_auth_error_state):
                last_post_otp_auth_error_state = dict(current_auth_error_state or {})
                _dump(
                    driver=driver,
                    kind="post_otp_auth_error_terminal",
                    message=(
                        f"wait-callback code={current_auth_error_state.get('code')} "
                        f"url={current_auth_error_state.get('url')}"
                    ),
                )
                return False
            try:
                if _try_recover_post_otp_auth_error(reason="wait-callback"):
                    if post_otp_auth_error_returned_to_auth_stage:
                        return False
                    end = max(end, time.time() + max(20, min(int(timeout), 45)))
                    time.sleep(1.0)
                    continue
            except Exception:
                pass
            time.sleep(0.5)
        try:
            WebDriverWait(driver, timeout).until(EC.url_contains("localhost:1455"))
            return True
        except Exception:
            pass
        if _click_consent_continue_if_needed():
            try:
                WebDriverWait(driver, timeout).until(EC.url_contains("localhost:1455"))
                return True
            except Exception:
                _dump(
                    driver=driver,
                    kind="consent_callback_timeout",
                    message="consent continue clicked but callback not reached",
                )
        current_auth_error_state = _auth_error_page_state()
        if _is_terminal_post_otp_auth_error(current_auth_error_state):
            last_post_otp_auth_error_state = dict(current_auth_error_state or {})
            _dump(
                driver=driver,
                kind="post_otp_auth_error_terminal",
                message=(
                    f"post-callback-timeout code={current_auth_error_state.get('code')} "
                    f"url={current_auth_error_state.get('url')}"
                ),
            )
            return False
        if _try_recover_post_otp_auth_error(reason="post-callback-timeout"):
            if post_otp_auth_error_returned_to_auth_stage:
                return False
            return _wait_callback_with_consent(timeout=max(20, min(int(timeout), 45)))
        return False

    if v != "CALLBACK":
        print(
            "[python-browser-service] waiting for OTP "
            f"candidate_count={len(mailbox_ref_candidates)}"
        )
        code, chosen_ref = _wait_code_try_candidates(
            candidates=mailbox_ref_candidates,
            min_mail_id_by_ref=otp_min_mail_id_by_ref,
            timeout_seconds=180,
            wait_openai_code_by_provider=wait_openai_code_by_provider,
            mailcreate_base_url=mailcreate_base_url,
            mailcreate_custom_auth=mailcreate_custom_auth,
            gptmail_base_url=gptmail_base_url,
            gptmail_api_key=gptmail_api_key,
            gptmail_keys_file=gptmail_keys_file,
            mailtm_api_base=mailtm_api_base,
        )
        native_code_submitted = False
        if str(browser_backend or "").strip().lower() == "camoufox":
            native_code_result = try_native_submit_code(driver, str(code), submit=True)
            if isinstance(native_code_result, dict) and native_code_result.get("ok"):
                print(f"[python-browser-service][repairer] native code primitive result={native_code_result}", flush=True)
                native_code_submitted = str(native_code_result.get("action") or "") not in ("", "filled")
        if not native_code_submitted:
            target = v
            if target == "CODE_STAGE":
                target = _code_input()
                if not target:
                    raise RuntimeError("code stage detected but no otp input located")
            _submit_code(target, code, tag="otp_submitted")
        else:
            _dump(driver=driver, kind="otp_submitted_native", message="otp submitted via native camoufox primitive")

        try:
            WebDriverWait(driver, 8).until(lambda _driver: _has_callback() or _has_incorrect_code_hint())
        except Exception:
            pass

        if _has_incorrect_code_hint():
            _raise_if_terminal_otp_rejection(tag_suffix="_post_submit")

    if not _wait_callback_with_consent():
        current_url = ""
        try:
            current_url = str(getattr(driver, "current_url", "") or "")
        except Exception:
            current_url = ""

        try:
            body_text = str(
                driver.execute_script(
                    "return document && document.body ? (document.body.innerText || '') : ''; "
                )
                or ""
            ).lower()
        except Exception:
            body_text = ""

        terminal_error = _email_verification_terminal_error(driver)
        if terminal_error:
            raise RuntimeError(terminal_error)

        auth_error_state = _auth_error_page_state()
        if auth_error_state:
            _dump(
                driver=driver,
                kind="auth_error_terminal",
                message=f"{auth_error_state.get('code')} url={auth_error_state.get('url')}",
            )
            raise RuntimeError(f"auth_error:{str(auth_error_state.get('code') or 'auth_error_page')}")

        if last_post_otp_auth_error_state:
            preserved_suffix = ""
            if post_otp_auth_error_returned_to_auth_stage:
                preserved_suffix = f" stage={post_otp_auth_error_returned_to_auth_stage}"
            _dump(
                driver=driver,
                kind="auth_error_terminal",
                message=(
                    f"{last_post_otp_auth_error_state.get('code')} "
                    f"url={last_post_otp_auth_error_state.get('url')} preserved=true{preserved_suffix}"
                ),
            )
            raise RuntimeError(
                f"auth_error:{str(last_post_otp_auth_error_state.get('code') or 'auth_error_page')}"
            )

        _dump(driver=driver, kind="callback_timeout", message="callback not reached after initial wait")

        if _has_incorrect_code_hint():
            _raise_if_terminal_otp_rejection(tag_suffix="_post_callback_timeout")

        _dump(driver=driver, kind="final_timeout", message="timeout waiting for oauth callback")

        if "account has been deleted or deactivated" in body_text or "account_deactivated" in body_text:
            raise RuntimeError("account_deactivated")

        raise RuntimeError(
            "timeout waiting for oauth callback "
            f"url={current_url!r}"
        )

    try:
        setattr(driver, "_neuro_repair_flow_result", {
            "mode": "legacy-fallback",
            "runner": "selenium-fallback" if str(browser_backend or "").strip().lower() == "camoufox" else "selenium",
        })
    except Exception:
        pass
    callback_url = str(getattr(driver, "current_url", "") or "")
    try:
        setattr(driver, "_neuro_finalize_callback_state", {
            "url": callback_url,
            "callbackMatched": "localhost:1455" in callback_url,
            "onConsentPage": False,
            "challengePresent": False,
        })
    except Exception:
        pass
    return callback_url, chosen_ref
