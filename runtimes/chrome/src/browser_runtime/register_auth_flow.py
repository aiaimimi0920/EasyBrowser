from __future__ import annotations

import inspect
import os
import re
import time
from typing import Any, Callable

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from .camoufox_native import (
    auth_surface_has_challenge,
    auth_surface_stage,
    inspect_auth_surface_on_driver,
    inspect_callback_state_on_driver,
    run_native_register_auth_flow,
    try_native_click_consent_continue,
    try_native_auth_fill_email,
    try_native_auth_fill_password,
    try_native_submit_code,
    wait_native_callback_with_consent,
    wait_native_code_or_callback,
)
from .turnstile_runtime import maybe_solve_turnstile_challenge


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


def run_register_auth_flow(
    driver,
    proxy=None,
    *,
    get_email: Callable[..., tuple[str, str]],
    generate_oauth_url: Callable[[], Any],
    _dbg: Callable[..., Any],
    _dump_page_body: Callable[..., Any],
    _raise_if_browser_network_error: Callable[..., Any],
    smart_wait: Callable[..., Any],
    _click_with_debug: Callable[..., Any],
    _human_mouse_jitter: Callable[..., Any],
    _human_type: Callable[..., Any],
    _human_delay: Callable[..., Any],
    generate_pwd: Callable[..., str],
    get_oai_code: Callable[..., str],
    OTP_TIMEOUT_SECONDS: int,
    captcha_provider: str | None = None,
    browser_backend: str | None = None,
) -> dict[str, Any]:
    email, address_jwt = get_email(proxy)
    _dbg("mailbox", f"obtained email={email} ref={address_jwt}", driver=driver)

    oauth_kwargs: dict[str, Any] = {}
    try:
        oauth_params = inspect.signature(generate_oauth_url).parameters
        if "driver" in oauth_params:
            oauth_kwargs["driver"] = driver
        if "proxy" in oauth_params:
            oauth_kwargs["proxy"] = proxy
    except Exception:
        oauth_kwargs = {}

    oauth = generate_oauth_url(**oauth_kwargs)
    url = oauth.auth_url
    _dbg("oauth", "generated oauth url", driver=driver)

    def _open_register_auth_context() -> None:
        _dbg("nav", "driver.get(oauth_url)", driver=driver)
        driver.get(url)

        try:
            nav_deadline = time.time() + 60
            while time.time() < nav_deadline:
                _raise_if_browser_network_error(driver, stage="wait_auth_openai")
                if "auth.openai.com" in str(getattr(driver, "current_url", "") or ""):
                    break
                time.sleep(0.5)
            else:
                raise TimeoutException("auth.openai.com not reached")
            _dbg("page", "reach oai sign up page", driver=driver)
        except TimeoutException:
            _dump_page_body(driver=driver, kind="wait_auth_openai", message="URL did not contain auth.openai.com")
            raise RuntimeError("did not reach auth.openai.com; page dumped")

        # click sign up; when the page variant does not expose a sign-up CTA,
        # keep the current auth context instead of forcing a redirect.
        cur_url0 = str(getattr(driver, "current_url", "") or "")
        if "auth.openai.com/log-in" in cur_url0:
            _dbg("ui", f"on login url, keep current auth context: {cur_url0}", driver=driver)

        try:
            sign_up_button = smart_wait(
                driver,
                By.XPATH,
                "//*[self::button or self::a][contains(normalize-space(), 'Sign up') or contains(normalize-space(), '注册') or contains(normalize-space(), 'Sign Up') or contains(normalize-space(), 'sign up') or contains(normalize-space(), 'SignUp')]",
                timeout=12,
                debug_kind="signup_button",
                debug_message="sign up button not found",
            )
            _dbg("ui", "click sign up", driver=driver)
            _click_with_debug(driver, sign_up_button, tag="signup_button", note="register click sign up")
            _dbg("ui", "sign up clicked", driver=driver)
        except Exception:
            # Some UI variants already land on create-account and won't render a Sign up CTA.
            # Also handle "创建密码" stage: do NOT redirect away from the current auth page.
            cur_url1 = str(getattr(driver, "current_url", "") or "")

            password_stage_now = False
            try:
                password_stage_now = bool(driver.execute_script(
                    """
                    const hasPwd = !!document.querySelector('input[type="password"],input[name*="password"],input[id*="password"]');
                    const t = (document && document.body && document.body.innerText) ? document.body.innerText : '';
                    return hasPwd || /创建密码|password|new password/i.test(t);
                    """
                ))
            except Exception:
                password_stage_now = False

            if password_stage_now:
                _dbg("ui", "signup cta missing but already on password stage, keep current page", driver=driver)
            else:
                _dbg("ui", f"signup cta missing, keep current page context: {cur_url1}", driver=driver)

    _open_register_auth_context()

    def _is_password_stage_page() -> bool:
        if str(browser_backend or "").strip().lower() == "camoufox":
            native_surface = inspect_auth_surface_on_driver(driver)
            if auth_surface_stage(native_surface) == "password":
                return True
        try:
            # Fast DOM-first detection
            found = driver.execute_script(
                """
                const sels = [
                  'input[type="password"]',
                  'input[name*="password"]',
                  'input[id*="password"]',
                  'input[autocomplete="new-password"]',
                  'input[autocomplete="current-password"]',
                  'input[aria-label*="password" i]',
                  'input[placeholder*="密码"]'
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

    def _snapshot_haystack(snapshot: dict[str, Any] | None) -> str:
        if not isinstance(snapshot, dict):
            return ""
        return "\n".join(
            [
                str(snapshot.get("url") or ""),
                str(snapshot.get("title") or ""),
                str(snapshot.get("body") or ""),
            ]
        ).lower()

    def _is_email_stage_page() -> bool:
        if _is_password_stage_page():
            return False
        try:
            found = driver.execute_script(
                """
                const sels = [
                  'input[type="email"]',
                  'input[name*="email"]',
                  'input[id*="email"]',
                  'input[autocomplete="email"]',
                  'input[placeholder*="email" i]'
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

        snapshot = _capture_auth_surface_snapshot()
        haystack = _snapshot_haystack(snapshot)
        current_url = str((snapshot or {}).get("url") or "").lower()
        return bool(
            ("auth.openai.com" in current_url or "chatgpt.com/auth" in current_url)
            and (
                "continue" in haystack
                or "create account" in haystack
                or "sign up" in haystack
                or "email" in haystack
            )
        )

    def _is_security_verification_snapshot(snapshot: dict[str, Any] | None) -> bool:
        haystack = _snapshot_haystack(snapshot)
        return bool(
            "just a moment" in haystack
            or "performing security verification" in haystack
            or "website uses a security service" in haystack
            or "performance and security by cloudflare" in haystack
            or "verify you are human" in haystack
            or "attention required" in haystack
        )

    def _is_broken_auth_surface(snapshot: dict[str, Any] | None) -> bool:
        haystack = _snapshot_haystack(snapshot)
        return bool(
            "err_empty_response" in haystack
            or "this page isn’t working" in haystack
            or "this page isn't working" in haystack
            or "didn’t send any data" in haystack
            or "didn't send any data" in haystack
            or "route error" in haystack
            or "invalid content type" in haystack
        )

    def _has_try_again_snapshot(snapshot: dict[str, Any] | None) -> bool:
        haystack = _snapshot_haystack(snapshot)
        return bool(
            "oops, an error occurred" in haystack
            or "try again" in haystack
            or "route error" in haystack
        )

    def _click_auth_retry_button() -> bool:
        selectors = (
            "//button[contains(translate(normalize-space(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'try again')]",
            "//a[contains(translate(normalize-space(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'try again')]",
            "//button[contains(translate(normalize-space(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'continue')]",
            "//a[contains(translate(normalize-space(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'continue')]",
        )
        for selector in selectors:
            try:
                for candidate in driver.find_elements(By.XPATH, selector):
                    if not candidate.is_displayed() or not candidate.is_enabled():
                        continue
                    _click_with_debug(driver, candidate, tag="auth_retry_button", note="retry auth surface")
                    return True
            except Exception:
                pass
        return False

    fallback_auth_urls = [
        str(url or "").strip(),
        "https://auth.openai.com/log-in-or-create-account",
        "https://auth.openai.com/log-in",
        "https://chatgpt.com/auth/login",
    ]

    def _recover_pre_email_auth_surface(stage_label: str, *, allow_fallback_nav: bool) -> bool:
        snapshot = _capture_auth_surface_snapshot()
        if snapshot is None:
            return False

        if _has_try_again_snapshot(snapshot):
            _dbg("ui", f"{stage_label} retry-surface snapshot={snapshot}", driver=driver)
            if _click_auth_retry_button():
                time.sleep(2.0)
                snapshot = _capture_auth_surface_snapshot()
                _dbg("ui", f"{stage_label} retry-surface resolved={snapshot}", driver=driver)
                if snapshot is not None and not (
                    _has_try_again_snapshot(snapshot)
                    or _is_broken_auth_surface(snapshot)
                ):
                    return True

        if _is_security_verification_snapshot(snapshot):
            _dbg("ui", f"{stage_label} security verification snapshot={snapshot}", driver=driver)
            if maybe_solve_turnstile_challenge(
                driver,
                provider_kind=captcha_provider,
                browser_backend=browser_backend,
                proxy=proxy,
                dbg_fn=_dbg,
            ):
                time.sleep(1.5)
                snapshot = _capture_auth_surface_snapshot()
                _dbg("ui", f"{stage_label} security verification solved={snapshot}", driver=driver)
                return True

            wait_deadline = time.time() + float(os.environ.get("AUTH_SECURITY_WAIT_SECONDS", "120") or "120")
            while time.time() < wait_deadline:
                time.sleep(2.0)
                snapshot = _capture_auth_surface_snapshot()
                if snapshot is None:
                    return False
                if not _is_security_verification_snapshot(snapshot):
                    _dbg("ui", f"{stage_label} security verification resolved={snapshot}", driver=driver)
                    return True
            return False

        if allow_fallback_nav and _is_broken_auth_surface(snapshot):
            current_url = str((snapshot or {}).get("url") or "").strip().lower()
            _dbg("ui", f"{stage_label} broken auth surface snapshot={snapshot}", driver=driver)
            for fallback_url in fallback_auth_urls:
                candidate = str(fallback_url or "").strip()
                if not candidate:
                    continue
                if current_url and candidate.lower() == current_url:
                    continue
                try:
                    driver.get(candidate)
                    time.sleep(3.0)
                except Exception:
                    continue
                snapshot = _capture_auth_surface_snapshot()
                if snapshot is None:
                    continue
                if _is_broken_auth_surface(snapshot):
                    continue
                _dbg("ui", f"{stage_label} fallback nav recovered via {candidate} snapshot={snapshot}", driver=driver)
                return True

        return False

    startup_recovery_rounds = int(os.environ.get("AUTH_STARTUP_RECOVERY_ROUNDS", "3") or "3")
    if startup_recovery_rounds < 1:
        startup_recovery_rounds = 1
    for _round in range(1, startup_recovery_rounds + 1):
        if _is_password_stage_page() or _is_email_stage_page():
            break
        recovered = _recover_pre_email_auth_surface(
            f"startup auth surface round={_round}/{startup_recovery_rounds}",
            allow_fallback_nav=True,
        )
        if not recovered and _round < startup_recovery_rounds:
            time.sleep(float(os.environ.get("DEBUG_EMAIL_RETRY_SLEEP_SECONDS", "2.0") or "2.0"))

    pwd = generate_pwd()
    if str(browser_backend or "").strip().lower() == "camoufox":
        try:
            native_auth_state = run_native_register_auth_flow(
                driver,
                email=email,
                address_jwt=address_jwt,
                oauth=oauth,
                password=pwd,
                fetch_code_fn=lambda: get_oai_code(
                    address_jwt=address_jwt,
                    timeout_seconds=OTP_TIMEOUT_SECONDS,
                    proxy=proxy,
                ),
                try_solve_challenge_fn=lambda reason: maybe_solve_turnstile_challenge(
                    driver,
                    provider_kind=captcha_provider,
                    browser_backend=browser_backend,
                    proxy=proxy,
                    dbg_fn=_dbg,
                ),
                callback_url_contains="chatgpt.com/api/auth/callback/openai",
            )
            _dbg(
                "auth",
                f"native register auth flow success mode={native_auth_state.get('mode')}",
                driver=driver,
            )
            try:
                _dump_page_body(
                    driver=driver,
                    kind="native_register_auth_flow_success",
                    message=f"mode={native_auth_state.get('mode')}",
                )
            except Exception:
                pass
            try:
                setattr(driver, "_neuro_register_auth_result", native_auth_state)
            except Exception:
                pass
            return native_auth_state
        except Exception as exc:
            _dbg("auth", f"native register auth flow fallback: {exc}", driver=driver)
            try:
                _dump_page_body(
                    driver=driver,
                    kind="native_register_auth_flow_fallback",
                    message=str(exc),
                )
            except Exception:
                pass
            _open_register_auth_context()

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
                      if (!/continue|create account|sign up|next|password|try again/i.test(txt)) continue;
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

    # fill email
    # In debug-visible mode, give create-account UI more settle time before first lookup.
    debug_visible = int(os.environ.get("HEADLESS", "1") or "1") == 0
    if debug_visible:
        time.sleep(float(os.environ.get("DEBUG_EMAIL_PREWAIT_SECONDS", "4.0") or "4.0"))

    email_wait_rounds = int(os.environ.get("DEBUG_EMAIL_WAIT_ROUNDS", "3" if debug_visible else "1") or ("3" if debug_visible else "1"))
    if email_wait_rounds < 1:
        email_wait_rounds = 1

    email_input = None
    last_email_err = None
    skip_email_submit = False
    native_email_submitted = False
    if str(browser_backend or "").strip().lower() == "camoufox":
        native_email_result = try_native_auth_fill_email(driver, email, submit=True)
        if isinstance(native_email_result, dict) and native_email_result.get("ok"):
            _dbg("ui", f"camoufox native email primitive result={native_email_result}", driver=driver)
            if str(native_email_result.get("emailValue") or "") == email and str(native_email_result.get("action") or "") not in ("", "filled"):
                native_email_submitted = True

    if native_email_submitted and not _is_password_stage_page():
        _dbg("ui", "native email primitive submitted, skip manual email fill", driver=driver)
        skip_email_submit = True

    for _round in range(1, email_wait_rounds + 1):
        if skip_email_submit:
            break
        # If UI already moved to password step, skip email stage.
        if _is_password_stage_page():
            skip_email_submit = True
            _dbg("ui", f"password stage detected before email fill, skip email round={_round}/{email_wait_rounds}", driver=driver)
            break
        if not _is_email_stage_page():
            recovered = _recover_pre_email_auth_surface(
                f"email wait round={_round}/{email_wait_rounds}",
                allow_fallback_nav=True,
            )
            if recovered and _is_password_stage_page():
                skip_email_submit = True
                _dbg("ui", f"password stage recovered before email fill round={_round}/{email_wait_rounds}", driver=driver)
                break

        # 1) First try a JS-visible selector sweep (more robust for dynamic id like _r_2_-email)
        try:
            email_input = driver.execute_script(
                """
                const sels = [
                  'input[type="email"]',
                  'input[name*="email"]',
                  'input[id*="email"]',
                  'input[placeholder*="邮箱"]',
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
            if email_input is not None:
                _dbg("ui", f"email input found by js sweep round={_round}/{email_wait_rounds}", driver=driver)
                break
        except Exception as e0:
            last_email_err = e0

        # 2) Then try existing wait locators
        try:
            email_input = smart_wait(
                driver,
                By.CSS_SELECTOR,
                'input[type="email"], input[name="email"], input[name*="email"], input[id$="-email"], input[id*="-email"], input[autocomplete="email"]',
                timeout=35 if debug_visible else 20,
                debug_kind="email_input",
                debug_message="email input not found",
            )
            break
        except Exception as e1:
            last_email_err = e1
            try:
                email_input = smart_wait(
                    driver,
                    By.CSS_SELECTOR,
                    'input[type="email"], input[name*="email"], input[id*="email"]',
                    timeout=30 if debug_visible else 15,
                    debug_kind="email_input_fallback",
                    debug_message="email input fallback not found",
                )
                break
            except Exception as e2:
                last_email_err = e2
                if _round < email_wait_rounds:
                    _dbg("ui", f"email input not ready, retry round={_round}/{email_wait_rounds}", driver=driver)
                    time.sleep(float(os.environ.get("DEBUG_EMAIL_RETRY_SLEEP_SECONDS", "2.0") or "2.0"))

    if not skip_email_submit:
        if email_input is None:
            if last_email_err is not None:
                raise last_email_err
            raise RuntimeError("email input not found after retries")
        _dbg("ui", "reach email input", driver=driver)
        _dbg("ui", f"fill email={email}", driver=driver)

        # Make email fill deterministic in visible debug mode:
        # 1) focus+clear
        # 2) JS set value + dispatch input/change
        # 3) verify value, fallback to human typing
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", email_input)
        except Exception:
            pass

        if debug_visible:
            _human_mouse_jitter(driver, attempts=3)
            _human_delay(0.45, 1.10)

        try:
            email_input.click()
        except Exception:
            try:
                driver.execute_script("arguments[0].focus();", email_input)
            except Exception:
                pass

        try:
            email_input.send_keys(Keys.CONTROL, "a")
            email_input.send_keys(Keys.BACKSPACE)
        except Exception:
            try:
                email_input.clear()
            except Exception:
                pass
        js_ok = False

        if debug_visible:
            _human_mouse_jitter(driver, attempts=2)
            _human_type(email_input, email, per_char_delay=(0.09, 0.22))
            _human_delay(0.25, 0.70)
            try:
                email_input.send_keys(Keys.TAB)
            except Exception:
                pass
            try:
                cur_v = str(getattr(email_input, "get_attribute", lambda _k: "")("value") or "")
                js_ok = (cur_v == email)
            except Exception:
                js_ok = False

        if not js_ok:
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
                    try {
                        const reactInput = new Event('input', { bubbles: true });
                        reactInput.simulated = true;
                        el.dispatchEvent(reactInput);
                    } catch (e) {}
                    try { el.dispatchEvent(new FocusEvent('blur', { bubbles: true })); } catch (e) {}
                    try { el.blur(); } catch (e) {}
                    return (el.value || '') === v;
                    """,
                    email_input,
                    email,
                )
                cur_v = str(getattr(email_input, "get_attribute", lambda _k: "")("value") or "")
                js_ok = (cur_v == email)
            except Exception:
                js_ok = False

        if not js_ok:
            _human_mouse_jitter(driver, attempts=2)
            _human_type(email_input, email)
            try:
                email_input.send_keys(Keys.TAB)
            except Exception:
                pass

        final_v = ""
        try:
            final_v = str(email_input.get_attribute("value") or "")
        except Exception:
            final_v = ""

        if final_v != email:
            raise RuntimeError(f"email not filled as expected: got={final_v!r} want={email!r}")

        _human_delay(0.15, 0.35)

        continue_btn = None
        try:
            continue_btn = smart_wait(
                driver,
                By.CSS_SELECTOR,
                'button[type="submit"][name="intent"][value="email"]',
                timeout=4,
                debug_kind="email_continue_button",
                debug_message="email continue button not found",
            )
        except Exception:
            continue_btn = None

        if continue_btn is None:
            try:
                continue_btn = driver.execute_script(
                    """
                    const selectors = [
                      'button[type="submit"]:not([disabled])',
                      'button[name="intent"][value="email"]:not([disabled])',
                      '[role="button"][data-action*="continue" i]',
                      '[role="button"][aria-label*="continue" i]'
                    ];
                    for (const s of selectors) {
                      const nodes = Array.from(document.querySelectorAll(s));
                      for (const n of nodes) {
                        const st = window.getComputedStyle(n);
                        const visible = st && st.display !== 'none' && st.visibility !== 'hidden' && n.offsetParent !== null;
                        const disabled = !!(n.disabled || n.getAttribute('aria-disabled') === 'true');
                        if (visible && !disabled) return n;
                      }
                    }
                    const nodes = Array.from(document.querySelectorAll('button,[role="button"]'));
                    for (const n of nodes) {
                      const t = (n.innerText || n.textContent || '').trim();
                      if (!t) continue;
                      if (!/\u7ee7\u7eed|continue/i.test(t)) continue;
                      const st = window.getComputedStyle(n);
                      const visible = st && st.display !== 'none' && st.visibility !== 'hidden' && n.offsetParent !== null;
                      const disabled = !!(n.disabled || n.getAttribute('aria-disabled') === 'true');
                      if (visible && !disabled) return n;
                    }
                    return null;
                    """
                )
            except Exception:
                continue_btn = None

        if continue_btn is not None:
            if debug_visible:
                _human_mouse_jitter(driver, attempts=2)
                _human_delay(0.55, 1.45)
            _click_with_debug(driver, continue_btn, tag="email_continue", note="submit email step")
            _dbg("ui", "email continue clicked", driver=driver)
        else:
            submitted = False
            if not debug_visible:
                try:
                    submitted = bool(driver.execute_script(
                        """
                        const el = arguments[0];
                        const form = el && typeof el.closest === 'function' ? el.closest('form') : null;
                        if (!form) return false;
                        try {
                          if (typeof form.requestSubmit === 'function') {
                            form.requestSubmit();
                            return true;
                          }
                        } catch (e) {}
                        try {
                          form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
                          form.submit();
                          return true;
                        } catch (e) {}
                        return false;
                        """,
                        email_input,
                    ))
                except Exception:
                    submitted = False

            if submitted:
                _dbg("ui", "email form submitted by fallback", driver=driver)
            else:
                if debug_visible:
                    _human_delay(0.35, 1.10)
                email_input.send_keys(Keys.ENTER)
                _dbg("ui", "email ENTER pressed (fallback)", driver=driver)
    else:
        _dbg("ui", "skip email stage because password page is already present", driver=driver)

    unified_followup_rounds = int(os.environ.get("DEBUG_UNIFIED_FOLLOWUP_ROUNDS", "4" if debug_visible else "2") or ("4" if debug_visible else "2"))
    if unified_followup_rounds < 1:
        unified_followup_rounds = 1
    for _round in range(1, unified_followup_rounds + 1):
        if _is_password_stage_page():
            _dbg("ui", f"password stage ready after email submit round={_round}/{unified_followup_rounds}", driver=driver)
            break
        if _is_unified_auth_context():
            snapshot = _capture_auth_surface_snapshot()
            if snapshot is not None and (_round == 1 or _round == unified_followup_rounds):
                _dbg("ui", f"unified auth snapshot round={_round}/{unified_followup_rounds} snapshot={snapshot}", driver=driver)
            if snapshot is not None and (
                _has_try_again_snapshot(snapshot)
                or _is_broken_auth_surface(snapshot)
                or _is_security_verification_snapshot(snapshot)
            ):
                recovered = _recover_pre_email_auth_surface(
                    f"unified auth followup round={_round}/{unified_followup_rounds}",
                    allow_fallback_nav=True,
                )
                if recovered and _is_password_stage_page():
                    _dbg(
                        "ui",
                        f"password stage recovered from unified auth followup round={_round}/{unified_followup_rounds}",
                        driver=driver,
                    )
                    break
            result = _resubmit_unified_email_stage(email)
            if result is not None:
                _dbg("ui", f"unified auth followup round={_round}/{unified_followup_rounds} result={result}", driver=driver)
        if _round < unified_followup_rounds:
            time.sleep(float(os.environ.get("DEBUG_PASSWORD_RETRY_SLEEP_SECONDS", "2.0") or "2.0"))

    # fill password
    def _is_human_verify_page() -> bool:
        if str(browser_backend or "").strip().lower() == "camoufox":
            native_surface = inspect_auth_surface_on_driver(driver)
            if auth_surface_has_challenge(native_surface) and auth_surface_stage(native_surface) != "password":
                return True
        try:
            # If password box is already visible, it's not blocked.
            has_pwd = bool(driver.execute_script(
                """
                const el = document.querySelector('input[type="password"],input[name*="password"],input[id*="password"]');
                if (!el) return false;
                const st = window.getComputedStyle(el);
                return !!(st && st.display !== 'none' && st.visibility !== 'hidden' && el.offsetParent !== null && !el.disabled);
                """
            ))
            if has_pwd:
                return False

            body_text_raw = str(
                driver.execute_script(
                    "return (document && document.body && document.body.innerText) ? document.body.innerText : '';"
                )
                or ""
            )
            body_text = body_text_raw.lower()
            title_text = str(driver.execute_script("return (document && document.title) ? document.title : '';") or "").lower()
            cur_url = str(getattr(driver, "current_url", "") or "").lower()

            # Strong signals only: avoid over-detecting by generic cloudflare/turnstile script presence.
            strong_url = (
                "cdn-cgi/challenge-platform" in cur_url
                or "/challenge" in cur_url
            )
            strong_text = (
                "verify you are human" in body_text
                or "performing security verification" in body_text
                or "just a moment" in body_text
                or "验证你是真人" in body_text_raw
                or "安全验证" in body_text_raw
            )
            strong_title = (
                "just a moment" in title_text
                or "attention required" in title_text
                or "verify" in title_text
            )
            return bool(strong_url or strong_text or strong_title)
        except Exception:
            return False

    pwd_wait_rounds = int(os.environ.get("DEBUG_PASSWORD_WAIT_ROUNDS", "3" if debug_visible else "1") or ("3" if debug_visible else "1"))
    if pwd_wait_rounds < 1:
        pwd_wait_rounds = 1

    challenge_grace_rounds = int(os.environ.get("DEBUG_CHALLENGE_GRACE_ROUNDS", "6" if debug_visible else "3") or ("6" if debug_visible else "3"))
    if challenge_grace_rounds < 1:
        challenge_grace_rounds = 1

    pwd_input = None
    last_pwd_err = None
    challenge_hits = 0
    native_password_submitted = False
    if str(browser_backend or "").strip().lower() == "camoufox":
        native_password_result = try_native_auth_fill_password(driver, "", submit=False)
        if isinstance(native_password_result, dict) and native_password_result.get("ok"):
            _dbg("ui", f"camoufox native password surface={native_password_result}", driver=driver)
    total_rounds = max(pwd_wait_rounds, challenge_grace_rounds)
    for _round in range(1, total_rounds + 1):
        if _is_human_verify_page():
            if maybe_solve_turnstile_challenge(
                driver,
                provider_kind=captcha_provider,
                browser_backend=browser_backend,
                proxy=proxy,
                dbg_fn=_dbg,
            ):
                challenge_hits = 0
                continue
            challenge_hits += 1
            _dbg("ui", f"possible challenge before password, grace wait round={challenge_hits}/{challenge_grace_rounds}", driver=driver)
            if challenge_hits >= challenge_grace_rounds:
                raise RuntimeError("blocked challenge page before password step")
            time.sleep(float(os.environ.get("DEBUG_PASSWORD_RETRY_SLEEP_SECONDS", "2.0") or "2.0"))
            continue

        try:
            pwd_input = driver.execute_script(
                """
                const sels = [
                  'input[type="password"]',
                  'input[name*="password"]',
                  'input[id*="password"]',
                  'input[autocomplete="new-password"]',
                  'input[autocomplete="current-password"]',
                  'input[aria-label*="password" i]',
                  'input[placeholder*="密码"]'
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
            if pwd_input is not None:
                _dbg("ui", f"password input found by js sweep round={_round}/{pwd_wait_rounds}", driver=driver)
                break
        except Exception as e0:
            last_pwd_err = e0

        try:
            pwd_input = smart_wait(
                driver,
                By.CSS_SELECTOR,
                'input[type="password"], input[name="new-password"], input[name*="password"], input[id$="-new-password"], input[id*="-password"], input[autocomplete="new-password"], input[autocomplete="current-password"], input[aria-label*="password" i]',
                timeout=30 if debug_visible else 20,
                debug_kind="password_input",
                debug_message=f"password input not found; email={email}",
            )
            break
        except Exception as e1:
            last_pwd_err = e1
            if _is_human_verify_page():
                if maybe_solve_turnstile_challenge(
                    driver,
                    provider_kind=captcha_provider,
                    browser_backend=browser_backend,
                    proxy=proxy,
                    dbg_fn=_dbg,
                ):
                    challenge_hits = 0
                    continue
                challenge_hits += 1
                _dbg("ui", f"possible challenge while waiting password input, grace round={challenge_hits}/{challenge_grace_rounds}", driver=driver)
                if challenge_hits >= challenge_grace_rounds:
                    raise RuntimeError("blocked challenge page before password step")
                time.sleep(float(os.environ.get("DEBUG_PASSWORD_RETRY_SLEEP_SECONDS", "2.0") or "2.0"))
                continue
            try:
                pwd_input = smart_wait(
                    driver,
                    By.CSS_SELECTOR,
                    'input[type="password"], input[name*="password"], input[id*="password"], input[autocomplete="new-password"], input[autocomplete="current-password"], input[aria-label*="password" i]',
                    timeout=20 if debug_visible else 12,
                    debug_kind="password_input_fallback",
                    debug_message=f"password input fallback not found; email={email}",
                )
                break
            except Exception as e2:
                last_pwd_err = e2
                if _round < total_rounds:
                    _dbg("ui", f"password input not ready, retry round={_round}/{total_rounds}", driver=driver)
                    time.sleep(float(os.environ.get("DEBUG_PASSWORD_RETRY_SLEEP_SECONDS", "2.0") or "2.0"))

    if pwd_input is None:
        # Last-resort fallback: on some variants, the password box is already focused
        # but attributes are dynamic and miss our selectors momentarily.
        try:
            ae = driver.switch_to.active_element
            ae_tag = str(getattr(ae, "tag_name", "") or "").lower()
            ae_type = str(ae.get_attribute("type") or "").lower()
            ae_disabled = str(ae.get_attribute("disabled") or "").lower()
            if ae_tag == "input" and ae_disabled not in ("true", "disabled") and ae_type in ("password", "text", ""):
                pwd_input = ae
                _dbg("ui", f"password input fallback to active_element type={ae_type}", driver=driver)
        except Exception:
            pass

    if pwd_input is None:
        if _is_human_verify_page():
            raise RuntimeError("blocked challenge page before password step")
        if last_pwd_err is not None:
            raise last_pwd_err
        raise RuntimeError(f"password input not found; email={email}")

    _dbg("ui", "reach password input", driver=driver)
    _dbg("ui", "fill password", driver=driver)

    if str(browser_backend or "").strip().lower() == "camoufox":
        native_password_result = try_native_auth_fill_password(driver, pwd, submit=True)
        if isinstance(native_password_result, dict) and native_password_result.get("ok"):
            _dbg("ui", f"camoufox native password primitive result={native_password_result}", driver=driver)
            if native_password_result.get("passwordFilled") and str(native_password_result.get("action") or "") not in ("", "filled"):
                native_password_submitted = True

    # Deterministic password fill (same strategy as email):
    # focus+clear -> JS set+events -> verify value -> fallback human typing.
    if not native_password_submitted:
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", pwd_input)
        except Exception:
            pass

        if debug_visible:
            _human_mouse_jitter(driver, attempts=3)
            _human_delay(0.55, 1.40)

        try:
            pwd_input.click()
        except Exception:
            try:
                driver.execute_script("arguments[0].focus();", pwd_input)
            except Exception:
                pass

        try:
            pwd_input.send_keys(Keys.CONTROL, "a")
            pwd_input.send_keys(Keys.BACKSPACE)
        except Exception:
            try:
                pwd_input.clear()
            except Exception:
                pass

    if not native_password_submitted:
        pwd_js_ok = False
        if debug_visible:
            _human_mouse_jitter(driver, attempts=2)
            _human_type(pwd_input, pwd, per_char_delay=(0.11, 0.26))
            _human_delay(0.45, 1.10)
            try:
                pwd_cur_v = str(getattr(pwd_input, "get_attribute", lambda _k: "")("value") or "")
                pwd_js_ok = (pwd_cur_v == pwd)
            except Exception:
                pwd_js_ok = False

        if not pwd_js_ok:
            try:
                driver.execute_script(
                    """
                    const el = arguments[0];
                    const v = arguments[1];
                    if (!el) return false;
                    el.focus();

                    // Use React-compatible setter to trigger internal state update
                    const nativeSetter = Object.getOwnPropertyDescriptor(
                        window.HTMLInputElement.prototype, 'value'
                    ).set;
                    nativeSetter.call(el, v);

                    // Dispatch events React listens on
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));

                    // Also try React 16+ specific event
                    try {
                        const ev = new Event('input', { bubbles: true });
                        ev.simulated = true;
                        el.dispatchEvent(ev);
                    } catch(e) {}

                    return (el.value || '') === v;
                    """,
                    pwd_input,
                    pwd,
                )
                pwd_cur_v = str(getattr(pwd_input, "get_attribute", lambda _k: "")("value") or "")
                pwd_js_ok = (pwd_cur_v == pwd)
            except Exception:
                pwd_js_ok = False

        if not pwd_js_ok:
            _human_mouse_jitter(driver, attempts=2)
            _human_type(pwd_input, pwd)

        pwd_final_v = ""
        try:
            pwd_final_v = str(pwd_input.get_attribute("value") or "")
        except Exception:
            pwd_final_v = ""

        if pwd_final_v != pwd:
            raise RuntimeError(f"password not filled as expected: got={pwd_final_v!r} want={pwd!r}")

        _human_delay(0.10, 0.30)

        # Prefer explicit continue button click on password page.
        try:
            pwd_continue_btn = smart_wait(
                driver,
                By.CSS_SELECTOR,
                'button[type="submit"], button[name="intent"][value="password"]',
                timeout=10,
                debug_kind="password_continue_button",
                debug_message=f"password continue button not found; email={email}",
            )
            if debug_visible:
                _human_mouse_jitter(driver, attempts=2)
                _human_delay(0.90, 2.20)
            _click_with_debug(driver, pwd_continue_btn, tag="password_continue", note="submit password step")
            _dbg("ui", "password continue clicked", driver=driver)
        except Exception:
            if debug_visible:
                _human_delay(0.60, 1.40)
            pwd_input.send_keys(Keys.ENTER)
            _dbg("ui", "password ENTER pressed (fallback)", driver=driver)
    else:
        _dbg("ui", "native password primitive submitted, skip manual password fill", driver=driver)

    # 严格流程顺序：先确认已进入验证码阶段（支持 URL/文案/输入框多信号），再去邮箱拉取验证码。
    otp_stage_ready = False
    otp_stage_reason = ""
    otp_wait_timeout = int(os.environ.get("OTP_STAGE_WAIT_SECONDS", "45") or "45")
    if otp_wait_timeout < 20:
        otp_wait_timeout = 20

    def _probe_otp_stage() -> tuple[bool, str, str, str]:
        cur_url = ""
        page_txt = ""
        native_surface = inspect_auth_surface_on_driver(driver) if str(browser_backend or "").strip().lower() == "camoufox" else None
        try:
            cur_url = str(getattr(driver, "current_url", "") or "")
        except Exception:
            cur_url = ""
        try:
            page_txt = str(driver.execute_script("return document && document.body ? (document.body.innerText || '') : ''; ") or "")
        except Exception:
            page_txt = ""

        if "email-verification" in cur_url:
            return True, "url=email-verification", cur_url, page_txt

        native_stage = auth_surface_stage(native_surface)
        if native_stage == "code":
            return True, "native_code_surface", cur_url, page_txt

        lower_txt = page_txt.lower()
        on_password_page = (
            "create-account/password" in cur_url.lower()
            or "create a password" in lower_txt
        )

        # Do not treat the password-page "one-time code" CTA as a real OTP stage.
        if not on_password_page and (
            "???" in page_txt
            or "???????" in page_txt
            or "????????" in page_txt
            or "verification code" in lower_txt
            or "check your inbox" in lower_txt
            or "resend email" in lower_txt
            or "enter code" in lower_txt
        ):
            return True, "page_text_hint", cur_url, page_txt

        try:
            els = driver.find_elements(
                By.CSS_SELECTOR,
                'input[autocomplete="one-time-code"], input[inputmode="numeric"][maxlength="6"], div[role="group"] input[inputmode="numeric"][maxlength="1"]',
            )
            if els:
                return True, "otp_input_found", cur_url, page_txt
        except Exception:
            pass

        return False, "", cur_url, page_txt

    def _retry_password_continue_once() -> bool:
        try:
            js_result = driver.execute_script(
                """
                return (function(){
                  const visible = (el) => {
                    if (!el) return false;
                    const st = window.getComputedStyle(el);
                    return !!(st && st.display !== 'none' && st.visibility !== 'hidden' && el.offsetParent !== null);
                  };
                  const textOf = (el) => ((el.innerText || el.textContent || '').trim());
                  const passwordInput = document.querySelector(
                    'input[type="password"], input[name*="password"], input[id*="password"], input[autocomplete="new-password"], input[autocomplete="current-password"]'
                  );
                  const candidates = Array.from(document.querySelectorAll('button, [role="button"], a, input[type="submit"]'));
                  for (const node of candidates) {
                    if (!visible(node)) continue;
                    const txt = textOf(node);
                    const value = String(node.getAttribute('value') || '');
                    const haystack = `${txt} ${value}`.toLowerCase();
                    if (!haystack) continue;
                    if (!/try again|one-time code|continue|next/.test(haystack)) continue;
                    try {
                      node.click();
                      return {
                        ok: true,
                        action: 'click_button',
                        label: txt || value,
                        url: String(location.href || ''),
                        body: String((document.body && document.body.innerText) || '').slice(0, 800),
                      };
                    } catch (e) {}
                  }

                  const form = passwordInput && typeof passwordInput.closest === 'function'
                    ? passwordInput.closest('form')
                    : document.querySelector('form[action*="/create-account/password"]');
                  if (form) {
                    try {
                      if (typeof form.requestSubmit === 'function') {
                        form.requestSubmit();
                        return {
                          ok: true,
                          action: 'request_submit',
                          url: String(location.href || ''),
                          body: String((document.body && document.body.innerText) || '').slice(0, 800),
                        };
                      }
                    } catch (e) {}
                    try {
                      form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
                      form.submit();
                      return {
                        ok: true,
                        action: 'form_submit',
                        url: String(location.href || ''),
                        body: String((document.body && document.body.innerText) || '').slice(0, 800),
                      };
                    } catch (e) {}
                  }

                  return { ok: false, action: 'none', url: String(location.href || '') };
                })();
                """
            )
            if isinstance(js_result, dict) and js_result.get("ok"):
                _dbg("ui", f"password retry primitive result={js_result}", driver=driver)
                return True
        except Exception:
            pass
        selectors = (
            'button[type="submit"]',
            'button[name="intent"][value="password"]',
        )
        for selector in selectors:
            try:
                for candidate in driver.find_elements(By.CSS_SELECTOR, selector):
                    if not candidate.is_displayed() or not candidate.is_enabled():
                        continue
                    _click_with_debug(driver, candidate, tag="password_continue_retry", note="retry password step")
                    return True
            except Exception:
                pass
        try:
            driver.switch_to.active_element.send_keys(Keys.ENTER)
            return True
        except Exception:
            return False

    def _click_one_time_code_recovery() -> bool:
        xpaths = (
            "//button[contains(translate(normalize-space(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'one-time code')]",
            "//a[contains(translate(normalize-space(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'one-time code')]",
            "//button[contains(normalize-space(), '验证码')]",
            "//a[contains(normalize-space(), '验证码')]",
        )
        for xpath in xpaths:
            try:
                for candidate in driver.find_elements(By.XPATH, xpath):
                    if not candidate.is_displayed() or not candidate.is_enabled():
                        continue
                    _click_with_debug(driver, candidate, tag="password_one_time_code_recovery", note="switch to one-time-code recovery")
                    return True
            except Exception:
                pass
        return False

    last_cur_url = ""
    last_page_txt = ""
    if str(browser_backend or "").strip().lower() == "camoufox":
        native_wait = wait_native_code_or_callback(
            driver,
            timeout_seconds=min(25, otp_wait_timeout),
            callback_url_contains="localhost:1455",
            try_solve_challenge_fn=lambda reason: maybe_solve_turnstile_challenge(
                driver,
                provider_kind=captcha_provider,
                browser_backend=browser_backend,
                proxy=proxy,
                dbg_fn=_dbg,
            ),
        )
        if native_wait.get("kind") == "code":
            otp_stage_ready = True
            otp_stage_reason = "native_wait_code"
        elif native_wait.get("kind") == "callback":
            otp_stage_ready = True
            otp_stage_reason = "native_wait_callback"
    end_ts = time.time() + otp_wait_timeout
    while (not otp_stage_ready) and time.time() < end_ts:
        otp_stage_ready, otp_stage_reason, last_cur_url, last_page_txt = _probe_otp_stage()
        if otp_stage_ready:
            break
        time.sleep(0.4)

    if not otp_stage_ready:
        lower_last_page = last_page_txt.lower()
        transient_password_failure = (
            (
                "create-account/password" in last_cur_url.lower()
                or "create a password" in lower_last_page
            )
            and (
                "failed to create account" in lower_last_page
                or "please try again" in lower_last_page
            )
        )
        if transient_password_failure:
            password_recovery_rounds = int(os.environ.get("PASSWORD_RECOVERY_ROUNDS", "3") or "3")
            if password_recovery_rounds < 1:
                password_recovery_rounds = 1
            for recovery_round in range(1, password_recovery_rounds + 1):
                used_one_time_code_recovery = _click_one_time_code_recovery()
                recovery_submitted = used_one_time_code_recovery or _retry_password_continue_once()
                if not recovery_submitted:
                    continue
                if used_one_time_code_recovery:
                    _dbg(
                        "ui",
                        f"password page reported transient create-account failure, switching to one-time-code recovery round={recovery_round}/{password_recovery_rounds}",
                        driver=driver,
                    )
                else:
                    _dbg(
                        "ui",
                        f"password page reported transient create-account failure, retrying continue round={recovery_round}/{password_recovery_rounds}",
                        driver=driver,
                    )
                retry_end_ts = time.time() + 12
                while (not otp_stage_ready) and time.time() < retry_end_ts:
                    otp_stage_ready, otp_stage_reason, last_cur_url, last_page_txt = _probe_otp_stage()
                    if otp_stage_ready:
                        retry_prefix = "password_one_time_code_recovery" if used_one_time_code_recovery else "password_retry"
                        otp_stage_reason = f"{retry_prefix}:{otp_stage_reason}"
                        break
                    time.sleep(0.4)
                if otp_stage_ready:
                    break

    if otp_stage_ready:
        _dbg("otp", f"otp stage ready ({otp_stage_reason}), now polling mailbox", driver=driver)
    else:
        try:
            _dump_page_body(driver=driver, kind="otp_stage_ready", message="password submitted but otp stage not ready")
        except Exception:
            pass
        raise RuntimeError("password submitted but otp stage not reached")

    _dbg("mail", f"start polling mailbox timeout={OTP_TIMEOUT_SECONDS}s", driver=driver)
    code = get_oai_code(address_jwt=address_jwt, timeout_seconds=OTP_TIMEOUT_SECONDS, proxy=proxy)
    # Dump page + pause shortly to reduce race where code changes due to resend.
    try:
        _dbg("mail", f"got verification code={code} mailbox_ref={address_jwt}", driver=driver)
    except Exception:
        pass
    time.sleep(1.0)
    def _wait_after_otp_submit(timeout: int = 25) -> bool:
        """Wait until we actually leave email-verification stage.

        Returns True when page likely accepted OTP and moved on.
        """

        if str(browser_backend or "").strip().lower() == "camoufox":
            if wait_native_callback_with_consent(
                driver,
                timeout_seconds=timeout,
                callback_url_contains="localhost:1455",
                try_solve_challenge_fn=lambda reason: maybe_solve_turnstile_challenge(
                    driver,
                    provider_kind=captcha_provider,
                    browser_backend=browser_backend,
                    proxy=proxy,
                    dbg_fn=_dbg,
                ),
            ):
                return True
        end_ts = time.time() + max(5, int(timeout))
        while time.time() < end_ts:
            if str(browser_backend or "").strip().lower() == "camoufox":
                callback_state = inspect_callback_state_on_driver(driver, callback_url_contains="localhost:1455")
                if isinstance(callback_state, dict):
                    if callback_state.get("callbackMatched"):
                        return True
                    if callback_state.get("onConsentPage"):
                        consent_result = try_native_click_consent_continue(driver)
                        if isinstance(consent_result, dict) and consent_result.get("ok"):
                            _dbg("ui", f"native consent primitive result={consent_result}", driver=driver)
                            time.sleep(0.8)
                            continue
            try:
                cur = str(getattr(driver, "current_url", "") or "")
            except Exception:
                cur = ""

            # Callback reached.
            if "localhost:1455" in cur:
                return True

            # Leave auth.openai email verification path.
            if "email-verification" not in cur and "auth.openai.com" in cur:
                return True

            # About-you form appears => OTP accepted.
            try:
                if driver.find_elements(By.CSS_SELECTOR, 'div[role="group"][id$="-birthday"]'):
                    return True
            except Exception:
                pass

            # Typical OTP error text means still on current stage.
            try:
                txt = str(driver.execute_script("return document && document.body ? (document.body.innerText || '') : ''; ") or "").lower()
                if "incorrect code" in txt or "invalid code" in txt:
                    return False
            except Exception:
                pass

            time.sleep(0.4)

        return False

    def _submit_code_segmented(code_str: str) -> None:
        code_inputs = WebDriverWait(driver, 10).until(
            lambda d: d.find_elements(
                By.CSS_SELECTOR,
                'div[role="group"] input[inputmode="numeric"][maxlength="1"]'
            )
        )
        if len(code_inputs) < 6:
            raise TimeoutException("segmented code inputs not enough")

        for current, digit in zip(code_inputs[:6], code_str[:6]):
            WebDriverWait(driver, 1).until(EC.element_to_be_clickable(current))
            _click_with_debug(driver, current, tag="otp_digit_box", note="register segmented otp input")
            try:
                current.clear()
            except Exception:
                pass
            current.send_keys(digit)

        time.sleep(0.2)
        try:
            driver.switch_to.active_element.send_keys(Keys.ENTER)
        except Exception:
            pass

    def _click_otp_continue() -> bool:
        continue_btn = None
        try:
            continue_btn = smart_wait(
                driver,
                By.CSS_SELECTOR,
                'button[type="submit"]:not([disabled]), button[name="intent"][value="email_otp"]:not([disabled])',
                timeout=8,
                debug_kind="otp_continue_button",
                debug_message="otp continue button not found",
            )
        except Exception:
            continue_btn = None

        if continue_btn is None:
            try:
                continue_btn = driver.execute_script(
                    """
                    const selectors = [
                      'button[type="submit"]:not([disabled])',
                      'button[name="intent"][value="email_otp"]:not([disabled])',
                      '[role="button"][data-action*="continue" i]',
                      '[role="button"][aria-label*="continue" i]'
                    ];
                    for (const s of selectors) {
                      const nodes = Array.from(document.querySelectorAll(s));
                      for (const n of nodes) {
                        const st = window.getComputedStyle(n);
                        const visible = st && st.display !== 'none' && st.visibility !== 'hidden' && n.offsetParent !== null;
                        const disabled = !!(n.disabled || n.getAttribute('aria-disabled') === 'true');
                        if (visible && !disabled) return n;
                      }
                    }
                    const nodes = Array.from(document.querySelectorAll('button,[role="button"]'));
                    for (const n of nodes) {
                      const t = (n.innerText || n.textContent || '').trim();
                      if (!t) continue;
                      if (!/continue/i.test(t)) continue;
                      const st = window.getComputedStyle(n);
                      const visible = st && st.display !== 'none' && st.visibility !== 'hidden' && n.offsetParent !== null;
                      const disabled = !!(n.disabled || n.getAttribute('aria-disabled') === 'true');
                      if (visible && !disabled) return n;
                    }
                    return null;
                    """
                )
            except Exception:
                continue_btn = None

        if continue_btn is None:
            return False

        if debug_visible:
            _human_mouse_jitter(driver, attempts=2)
            _human_delay(0.25, 0.75)
        _click_with_debug(driver, continue_btn, tag="otp_continue", note="submit otp step")
        _dbg("ui", "otp continue clicked", driver=driver)
        return True

    try:
        used_segmented = False
        native_code_submitted = False
        code_input = None

        try:
            code_input = smart_wait(
                driver,
                By.ID,
                "_r_4_-code",
                timeout=10,
                debug_kind="code_input",
                debug_message="Timeout waiting for code input",
            )
        except Exception:
            try:
                code_input = smart_wait(
                    driver,
                    By.CSS_SELECTOR,
                    'input[autocomplete="one-time-code"], input[inputmode="numeric"][maxlength="6"], input[name*="code" i], input[id*="code" i]',
                    timeout=10,
                    debug_kind="code_input_fallback",
                    debug_message="Timeout waiting for code input fallback",
                )
            except Exception:
                code_input = None
                try:
                    candidates = driver.find_elements(
                        By.CSS_SELECTOR,
                        'input[autocomplete="one-time-code"], input[inputmode="numeric"][maxlength="6"], input[name*="code" i], input[id*="code" i]',
                    )
                except Exception:
                    candidates = []

                for candidate in candidates:
                    try:
                        if candidate.is_enabled():
                            code_input = candidate
                            break
                    except Exception:
                        code_input = candidate
                        break

                if code_input is None:
                    try:
                        code_input = driver.execute_script(
                            """
                            return document.querySelector(
                              'input[autocomplete="one-time-code"], ' +
                              'input[inputmode="numeric"][maxlength="6"], ' +
                              'input[name*="code" i], input[id*="code" i]'
                            );
                            """
                        )
                    except Exception:
                        code_input = None

                if code_input is None:
                    raise

                _dbg("wait", "code_input_fallback recovered via direct DOM lookup", driver=driver)


        # Defensive: ensure the code input is empty.
        try:
            code_input.clear()
        except Exception:
            try:
                code_input.send_keys(Keys.CONTROL + "a")
                code_input.send_keys(Keys.BACKSPACE)
            except Exception:
                pass

        # Sanity-check: the page should be sending to the same email.
        try:
            page_txt = driver.execute_script("return document && document.body ? document.body.innerText : ''; ")
            m = re.search(
                r"sent\s+to\s+([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})",
                str(page_txt or ""),
                flags=re.IGNORECASE,
            )
            if m:
                page_email = (m.group(1) or "").strip().lower()
                if page_email and page_email != (email or "").strip().lower():
                    _dbg("code", f"page email mismatch page={page_email} expected={email}", driver=driver)
                    _dump_page_body(driver=driver, kind="code_email_mismatch", message=f"page={page_email} expected={email}")
        except Exception:
            pass

        if str(browser_backend or "").strip().lower() == "camoufox":
            native_code_result = try_native_submit_code(driver, str(code), submit=True)
            if isinstance(native_code_result, dict) and native_code_result.get("ok"):
                _dbg("ui", f"camoufox native code primitive result={native_code_result}", driver=driver)
                native_code_submitted = str(native_code_result.get("action") or "") not in ("", "filled")
                used_segmented = native_code_result.get("mode") == "segmented"

        typed_val = ""
        if not native_code_submitted:
            # Try single-input first.
            try:
                if debug_visible:
                    try:
                        code_input.click()
                    except Exception:
                        pass
                    _human_mouse_jitter(driver, attempts=1)
                    _human_delay(0.12, 0.35)
                    _human_type(code_input, code, per_char_delay=(0.08, 0.18))
                else:
                    code_input.send_keys(code)
                typed_val = str(code_input.get_attribute("value") or "")
            except Exception:
                typed_val = ""

            if len(re.sub(r"\D", "", typed_val)) < 6:
                try:
                    typed_val = str(
                        driver.execute_script(
                            """
                            const el = arguments[0];
                            const value = String(arguments[1] || '');
                            try { el.focus(); } catch (e) {}
                            try { el.value = value; } catch (e) {}
                            try { el.dispatchEvent(new Event('input', { bubbles: true })); } catch (e) {}
                            try { el.dispatchEvent(new Event('change', { bubbles: true })); } catch (e) {}
                            return el.value || '';
                            """,
                            code_input,
                            code,
                        )
                        or ""
                    )
                except Exception:
                    typed_val = typed_val or ""

            # If value isn't really present, switch to segmented mode.
            if len(re.sub(r"\D", "", typed_val)) < 6:
                _dbg("code", f"single otp input not accepted typed='{typed_val}' -> segmented fallback", driver=driver)
                _submit_code_segmented(str(code))
                used_segmented = True
            else:
                time.sleep(0.6 if debug_visible else 0.2)
                if not _click_otp_continue():
                    code_input.send_keys(Keys.ENTER)

        try:
            _dump_page_body(
                driver=driver,
                kind="otp_submitted",
                message=f"code_submitted used_segmented={used_segmented} native={native_code_submitted}",
            )
        except Exception:
            pass

        accepted = _wait_after_otp_submit(timeout=25)
        if not accepted:
            terminal_error = _email_verification_terminal_error(driver)
            if terminal_error:
                _dump_page_body(driver=driver, kind="otp_terminal_rejection", message=terminal_error)
                raise RuntimeError(terminal_error)
            _dump_page_body(driver=driver, kind="otp_not_accepted", message=f"code_submitted used_segmented={used_segmented}")
            raise RuntimeError("otp submitted but page did not advance")
        try:
            _dump_page_body(
                driver=driver,
                kind="otp_accepted",
                message=f"code_accepted used_segmented={used_segmented}",
            )
        except Exception:
            pass

        # Treat explicit OTP rejection as terminal. Continuing only burns time.
        try:
            terminal_error = _email_verification_terminal_error(driver)
            if terminal_error:
                _dbg("code", f"detected terminal email verification rejection: {terminal_error}", driver=driver)
                _dump_page_body(driver=driver, kind="otp_terminal_rejection", message=terminal_error)
                raise RuntimeError(terminal_error)
        except Exception:
            raise

    except TimeoutException:
        _submit_code_segmented(str(code))
        if not _wait_after_otp_submit(timeout=25):
            _dump_page_body(driver=driver, kind="otp_not_accepted_segmented", message="segmented otp submitted but page did not advance")
            raise RuntimeError("segmented otp submitted but page did not advance")


    auth_result = {
        "email": email,
        "address_jwt": address_jwt,
        "oauth": oauth,
        "pwd": pwd,
        "mode": "legacy-fallback",
        "runner": str(browser_backend or "").strip().lower() == "camoufox" and "selenium-fallback" or "selenium",
    }
    try:
        setattr(driver, "_neuro_register_auth_result", auth_result)
    except Exception:
        pass
    return auth_result
