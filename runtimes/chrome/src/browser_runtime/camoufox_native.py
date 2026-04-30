from __future__ import annotations

import os
import tempfile
import time
from typing import Any
from urllib.parse import unquote, urlparse

try:
    from patchright.sync_api import sync_playwright  # type: ignore
    _PATCHRIGHT_SYNC_IMPORT_ERROR: str | None = None
except Exception as exc:  # pragma: no cover
    sync_playwright = None  # type: ignore[assignment]
    _PATCHRIGHT_SYNC_IMPORT_ERROR = str(exc)


def patchright_sync_available() -> bool:
    return sync_playwright is not None


def patchright_sync_import_error() -> str | None:
    return _PATCHRIGHT_SYNC_IMPORT_ERROR


def native_camoufox_enabled() -> bool:
    return (os.environ.get("CAMOUFOX_NATIVE_EXECUTOR") or "1").strip().lower() not in ("0", "false", "no", "off")


def native_camoufox_preferred() -> bool:
    return (os.environ.get("CAMOUFOX_NATIVE_PREFER") or "1").strip().lower() not in ("0", "false", "no", "off")


def native_camoufox_isolated_profile() -> bool:
    return (os.environ.get("CAMOUFOX_NATIVE_ISOLATED_PROFILE") or "1").strip().lower() not in ("0", "false", "no", "off")


def describe_native_camoufox_executor() -> dict[str, Any]:
    return {
        "enabled": native_camoufox_enabled(),
        "preferred": native_camoufox_preferred(),
        "isolatedProfile": native_camoufox_isolated_profile(),
        "patchrightSyncAvailable": patchright_sync_available(),
        "patchrightSyncImportError": patchright_sync_import_error(),
    }


def ensure_native_camoufox_profile_root() -> tuple[str, str]:
    root_dir = tempfile.mkdtemp(prefix="camoufox_native_")
    profile_dir = os.path.join(root_dir, "profile")
    os.makedirs(profile_dir, exist_ok=True)
    return root_dir, profile_dir


def _proxy_settings(proxy_raw: str | None) -> dict[str, Any] | None:
    raw = str(proxy_raw or "").strip()
    if not raw:
        return None
    parsed = urlparse(raw)
    if not parsed.hostname or not parsed.port:
        raise ValueError(f"invalid proxy url: {raw}")
    settings: dict[str, Any] = {
        "server": f"{parsed.scheme or 'http'}://{parsed.hostname}:{parsed.port}",
    }
    if parsed.username:
        settings["username"] = unquote(parsed.username)
    if parsed.password:
        settings["password"] = unquote(parsed.password)
    return settings


def _block_resource(resource_type: str) -> bool:
    normalized = str(resource_type or "").strip().lower()
    if normalized in ("image", "imageset", "media"):
        return (os.environ.get("CAMOUFOX_NATIVE_BLOCK_IMAGES") or "0").strip().lower() not in ("0", "false", "no", "off")
    if normalized == "stylesheet":
        return (os.environ.get("CAMOUFOX_NATIVE_BLOCK_CSS") or "0").strip().lower() not in ("0", "false", "no", "off")
    if normalized == "font":
        return (os.environ.get("CAMOUFOX_NATIVE_BLOCK_FONTS") or "0").strip().lower() not in ("0", "false", "no", "off")
    return False


def prime_native_camoufox_profile(
    *,
    user_data_dir: str,
    startup_url: str | None = None,
    proxy: str | None = None,
    user_agent: str | None = None,
) -> dict[str, Any]:
    if not native_camoufox_enabled():
        raise RuntimeError("native camoufox executor is disabled")
    if sync_playwright is None:
        raise RuntimeError(f"patchright sync api unavailable: {_PATCHRIGHT_SYNC_IMPORT_ERROR or 'not installed'}")

    profile_dir = str(user_data_dir or "").strip()
    if not profile_dir:
        raise ValueError("user_data_dir is required for native camoufox bootstrap")
    os.makedirs(profile_dir, exist_ok=True)

    start_ts = time.time()
    target_url = str(startup_url or "").strip() or None
    timeout_ms = max(5_000, int((os.environ.get("CAMOUFOX_NATIVE_TIMEOUT_MS") or "45000").strip() or "45000"))
    headless = (os.environ.get("CAMOUFOX_NATIVE_HEADLESS") or "1").strip().lower() not in ("0", "false", "no", "off")
    channel = (os.environ.get("CAMOUFOX_NATIVE_CHANNEL") or "chrome").strip() or "chrome"
    locale = (os.environ.get("CAMOUFOX_NATIVE_LOCALE") or "en-US").strip() or "en-US"
    timezone_id = (os.environ.get("CAMOUFOX_NATIVE_TIMEZONE_ID") or "UTC").strip() or "UTC"
    viewport = {
        "width": int((os.environ.get("CAMOUFOX_NATIVE_VIEWPORT_WIDTH") or "1365").strip() or "1365"),
        "height": int((os.environ.get("CAMOUFOX_NATIVE_VIEWPORT_HEIGHT") or "1024").strip() or "1024"),
    }

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            channel=channel if channel != "camoufox" else "chrome",
            headless=headless,
            proxy=_proxy_settings(proxy),
            viewport=viewport,
            user_agent=user_agent or None,
            locale=locale,
            timezone_id=timezone_id,
            color_scheme="light",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-popup-blocking",
                "--disable-renderer-backgrounding",
                "--disable-backgrounding-occluded-windows",
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-site-isolation-trials",
            ],
        )
        try:
            context.route(
                "**/*",
                lambda route: route.abort() if _block_resource(str(route.request.resource_type or "")) else route.continue_(),
            )
        except Exception:
            pass

        page = context.pages[0] if context.pages else context.new_page()
        if target_url:
            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=timeout_ms)
            except Exception:
                pass
        try:
            page.wait_for_timeout(800)
        except Exception:
            pass
        try:
            resolved_user_agent = str(page.evaluate("() => navigator.userAgent || ''") or "").strip()
        except Exception:
            resolved_user_agent = str(user_agent or "").strip()
        try:
            cookie_count = len(context.cookies())
        except Exception:
            cookie_count = 0
        try:
            current_url = str(page.url or "").strip()
        except Exception:
            current_url = target_url or ""
        try:
            title = str(page.title() or "").strip()
        except Exception:
            title = ""
        try:
            auth_surface = page.evaluate(
                """
                () => {
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
                  ];
                  const passwordSelectors = [
                    'input[type="password"]',
                    'input[name*="password"]',
                    'input[id*="password"]',
                    'input[autocomplete="current-password"]',
                    'input[autocomplete="new-password"]',
                  ];
                  const hasVisible = (selectors) => selectors.some((sel) => {
                    const node = document.querySelector(sel);
                    return visible(node);
                  });
                  const buttons = Array.from(document.querySelectorAll('button,[role="button"],a'))
                    .filter(visible)
                    .map((node) => textOf(node))
                    .filter(Boolean)
                    .slice(0, 8);
                  const body = String((document.body && document.body.innerText) || '').replace(/\\s+/g, ' ').trim().slice(0, 400);
                  return {
                    url: String(location.href || ''),
                    title: String(document.title || ''),
                    emailInputVisible: hasVisible(emailSelectors),
                    passwordInputVisible: hasVisible(passwordSelectors),
                    buttonTexts: buttons,
                    challengePresent: /turnstile|verify you are human|just a moment|challenge/i.test(body),
                    bodyExcerpt: body,
                  };
                }
                """
            )
        except Exception:
            auth_surface = None
        context.close()

    duration_ms = int((time.time() - start_ts) * 1000)
    return {
        "primed": True,
        "profileDir": profile_dir,
        "startupUrl": target_url,
        "currentUrl": current_url,
        "title": title,
        "userAgent": resolved_user_agent,
        "cookieCount": cookie_count,
        "durationMs": duration_ms,
        "channel": channel,
        "headless": headless,
        "authSurface": auth_surface,
    }


def inspect_auth_surface_on_driver(driver) -> dict[str, Any] | None:
    try:
        payload = driver.execute_script(
            """
            return (function(){
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
              const passwordSelectors = [
                'input[type="password"]',
                'input[name*="password"]',
                'input[id*="password"]',
                'input[autocomplete="current-password"]',
                'input[autocomplete="new-password"]',
                'input[aria-label*="password" i]'
              ];
              const codeSelectors = [
                'input[id*="code"]',
                'input[name*="code"]',
                'input[autocomplete="one-time-code"]',
                'input[inputmode="numeric"][maxlength="6"]',
                'input[aria-label*="code" i]',
                'input[placeholder*="code" i]'
              ];
              const firstVisible = (selectors) => {
                for (const sel of selectors) {
                  const node = document.querySelector(sel);
                  if (visible(node) && !node.disabled) return node;
                }
                return null;
              };
              const body = String((document.body && document.body.innerText) || '').replace(/\\s+/g, ' ').trim().slice(0, 1200);
              const buttons = Array.from(document.querySelectorAll('button,[role="button"],a'))
                .filter(visible)
                .map((node) => textOf(node))
                .filter(Boolean)
                .slice(0, 12);
              return {
                url: String(location.href || ''),
                title: String(document.title || ''),
                emailInputVisible: !!firstVisible(emailSelectors),
                passwordInputVisible: !!firstVisible(passwordSelectors),
                codeInputVisible: !!firstVisible(codeSelectors),
                buttonTexts: buttons,
                challengePresent: /turnstile|verify you are human|just a moment|performing security verification|challenge/i.test(body),
                bodyExcerpt: body,
              };
            })();
            """
        )
    except Exception:
        payload = None
    return payload if isinstance(payload, dict) else None


def auth_surface_stage(surface: dict[str, Any] | None) -> str:
    if not isinstance(surface, dict):
        return "unknown"
    if bool(surface.get("challengePresent")) and not bool(surface.get("passwordInputVisible")) and not bool(surface.get("emailInputVisible")):
        return "challenge"
    if bool(surface.get("passwordInputVisible")):
        return "password"
    if bool(surface.get("codeInputVisible")):
        return "code"
    if bool(surface.get("emailInputVisible")):
        return "email"
    return "unknown"


def auth_surface_has_challenge(surface: dict[str, Any] | None) -> bool:
    return bool(isinstance(surface, dict) and surface.get("challengePresent"))


def try_native_auth_fill_email(driver, email: str, *, submit: bool = True) -> dict[str, Any] | None:
    try:
        payload = driver.execute_script(
            """
            return (function(expectedEmail, shouldSubmit){
              const visible = (el) => {
                if (!el) return false;
                const st = window.getComputedStyle(el);
                return !!(st && st.display !== 'none' && st.visibility !== 'hidden' && el.offsetParent !== null);
              };
              const textOf = (el) => ((el.innerText || el.textContent || '').trim());
              const selectors = [
                'input[type="email"]',
                'input[name*="email"]',
                'input[id*="email"]',
                'input[autocomplete="email"]',
                'input[autocomplete="username"]',
                'input[placeholder*="email" i]'
              ];
              let input = null;
              for (const sel of selectors) {
                const node = document.querySelector(sel);
                if (visible(node) && !node.disabled) {
                  input = node;
                  break;
                }
              }
              if (!input) {
                return { ok: false, stage: 'missing-email', url: String(location.href || '') };
              }

              const proto = (input.tagName || '').toLowerCase() === 'textarea'
                ? window.HTMLTextAreaElement.prototype
                : window.HTMLInputElement.prototype;
              const nativeSetter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
              try {
                input.focus();
              } catch (e) {}
              if (typeof nativeSetter === 'function') {
                nativeSetter.call(input, expectedEmail);
              } else {
                input.value = expectedEmail;
              }
              input.dispatchEvent(new Event('input', { bubbles: true }));
              input.dispatchEvent(new Event('change', { bubbles: true }));
              try { input.dispatchEvent(new FocusEvent('blur', { bubbles: true })); } catch (e) {}
              try { input.blur(); } catch (e) {}

              let action = 'filled';
              let buttonText = '';
              if (shouldSubmit) {
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
                    if (!/continue|create account|sign up|next|password/i.test(txt)) continue;
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
                if (action === 'filled') {
                  try {
                    const form = input.closest('form');
                    if (form && typeof form.requestSubmit === 'function') {
                      form.requestSubmit();
                      action = 'request_submit';
                    } else if (form) {
                      form.submit();
                      action = 'form_submit';
                    }
                  } catch (e) {}
                }
                if (action === 'filled') {
                  try {
                    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true }));
                    input.dispatchEvent(new KeyboardEvent('keypress', { key: 'Enter', code: 'Enter', bubbles: true }));
                    input.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', bubbles: true }));
                    action = 'dispatch_enter';
                  } catch (e) {}
                }
              }
              return {
                ok: true,
                stage: 'email',
                action,
                buttonText,
                emailValue: String(input.value || ''),
                url: String(location.href || ''),
              };
            })(arguments[0], arguments[1]);
            """,
            str(email or ""),
            bool(submit),
        )
    except Exception:
        payload = None
    return payload if isinstance(payload, dict) else None


def try_native_auth_fill_password(driver, password: str, *, submit: bool = True) -> dict[str, Any] | None:
    try:
        payload = driver.execute_script(
            """
            return (function(expectedPassword, shouldSubmit){
              const visible = (el) => {
                if (!el) return false;
                const st = window.getComputedStyle(el);
                return !!(st && st.display !== 'none' && st.visibility !== 'hidden' && el.offsetParent !== null);
              };
              const textOf = (el) => ((el.innerText || el.textContent || '').trim());
              const selectors = [
                'input[type="password"]',
                'input[name*="password"]',
                'input[id*="password"]',
                'input[autocomplete="current-password"]',
                'input[autocomplete="new-password"]',
                'input[aria-label*="password" i]'
              ];
              let input = null;
              for (const sel of selectors) {
                const node = document.querySelector(sel);
                if (visible(node) && !node.disabled) {
                  input = node;
                  break;
                }
              }
              if (!input) {
                return { ok: false, stage: 'missing-password', url: String(location.href || '') };
              }
              const proto = (input.tagName || '').toLowerCase() === 'textarea'
                ? window.HTMLTextAreaElement.prototype
                : window.HTMLInputElement.prototype;
              const nativeSetter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
              try {
                input.focus();
              } catch (e) {}
              if (typeof nativeSetter === 'function') {
                nativeSetter.call(input, expectedPassword);
              } else {
                input.value = expectedPassword;
              }
              input.dispatchEvent(new Event('input', { bubbles: true }));
              input.dispatchEvent(new Event('change', { bubbles: true }));
              try { input.dispatchEvent(new FocusEvent('blur', { bubbles: true })); } catch (e) {}
              try { input.blur(); } catch (e) {}

              let action = 'filled';
              let buttonText = '';
              if (shouldSubmit) {
                const candidateSelectors = [
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
                    if (!/continue|password|log in|login|next|verify/i.test(txt)) continue;
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
                if (action === 'filled') {
                  try {
                    const form = input.closest('form');
                    if (form && typeof form.requestSubmit === 'function') {
                      form.requestSubmit();
                      action = 'request_submit';
                    } else if (form) {
                      form.submit();
                      action = 'form_submit';
                    }
                  } catch (e) {}
                }
                if (action === 'filled') {
                  try {
                    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true }));
                    input.dispatchEvent(new KeyboardEvent('keypress', { key: 'Enter', code: 'Enter', bubbles: true }));
                    input.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', bubbles: true }));
                    action = 'dispatch_enter';
                  } catch (e) {}
                }
              }
              return {
                ok: true,
                stage: 'password',
                action,
                buttonText,
                passwordFilled: String(input.value || '') === expectedPassword,
                url: String(location.href || ''),
              };
            })(arguments[0], arguments[1]);
            """,
            str(password or ""),
            bool(submit),
        )
    except Exception:
        payload = None
    return payload if isinstance(payload, dict) else None


def try_native_submit_code(driver, code: str, *, submit: bool = True) -> dict[str, Any] | None:
    try:
        payload = driver.execute_script(
            """
            return (function(expectedCode, shouldSubmit){
              const visible = (el) => {
                if (!el) return false;
                const st = window.getComputedStyle(el);
                return !!(st && st.display !== 'none' && st.visibility !== 'hidden' && el.offsetParent !== null);
              };
              const singleSelectors = [
                'input[autocomplete="one-time-code"]',
                'input[inputmode="numeric"][maxlength="6"]',
                'input[name*="code" i]',
                'input[id*="code" i]',
                'input[aria-label*="code" i]',
                'input[placeholder*="code" i]'
              ];
              const segmentedSelectors = [
                'div[role="group"] input[inputmode="numeric"][maxlength="1"]'
              ];

              let single = null;
              for (const sel of singleSelectors) {
                const node = document.querySelector(sel);
                if (visible(node) && !node.disabled) {
                  single = node;
                  break;
                }
              }

              let segmented = [];
              for (const sel of segmentedSelectors) {
                segmented = Array.from(document.querySelectorAll(sel)).filter((node) => visible(node) && !node.disabled);
                if (segmented.length >= 6) break;
              }

              if (!single && segmented.length < 6) {
                return { ok: false, stage: 'missing-code', url: String(location.href || '') };
              }

              let mode = 'single';
              let action = 'filled';
              if (single) {
                const proto = (single.tagName || '').toLowerCase() === 'textarea'
                  ? window.HTMLTextAreaElement.prototype
                  : window.HTMLInputElement.prototype;
                const nativeSetter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
                try { single.focus(); } catch (e) {}
                if (typeof nativeSetter === 'function') {
                  nativeSetter.call(single, expectedCode);
                } else {
                  single.value = expectedCode;
                }
                single.dispatchEvent(new Event('input', { bubbles: true }));
                single.dispatchEvent(new Event('change', { bubbles: true }));
                try { single.dispatchEvent(new FocusEvent('blur', { bubbles: true })); } catch (e) {}
                try { single.blur(); } catch (e) {}
                if (shouldSubmit) {
                  try {
                    const form = single.closest('form');
                    if (form && typeof form.requestSubmit === 'function') {
                      form.requestSubmit();
                      action = 'request_submit';
                    } else if (form) {
                      form.submit();
                      action = 'form_submit';
                    }
                  } catch (e) {}
                  if (action === 'filled') {
                    try {
                      single.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true }));
                      single.dispatchEvent(new KeyboardEvent('keypress', { key: 'Enter', code: 'Enter', bubbles: true }));
                      single.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', bubbles: true }));
                      action = 'dispatch_enter';
                    } catch (e) {}
                  }
                }
                return {
                  ok: true,
                  stage: 'code',
                  mode,
                  action,
                  codeValue: String(single.value || ''),
                  url: String(location.href || ''),
                };
              }

              mode = 'segmented';
              const digits = String(expectedCode || '').replace(/\\D+/g, '').slice(0, 6).split('');
              segmented.slice(0, digits.length).forEach((node, idx) => {
                const digit = digits[idx] || '';
                const proto = (node.tagName || '').toLowerCase() === 'textarea'
                  ? window.HTMLTextAreaElement.prototype
                  : window.HTMLInputElement.prototype;
                const nativeSetter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
                try { node.focus(); } catch (e) {}
                if (typeof nativeSetter === 'function') {
                  nativeSetter.call(node, digit);
                } else {
                  node.value = digit;
                }
                node.dispatchEvent(new Event('input', { bubbles: true }));
                node.dispatchEvent(new Event('change', { bubbles: true }));
              });
              if (shouldSubmit) {
                try {
                  const last = segmented[Math.min(segmented.length - 1, Math.max(0, digits.length - 1))];
                  last.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true }));
                  last.dispatchEvent(new KeyboardEvent('keypress', { key: 'Enter', code: 'Enter', bubbles: true }));
                  last.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', bubbles: true }));
                  action = 'dispatch_enter';
                } catch (e) {}
              }
              return {
                ok: true,
                stage: 'code',
                mode,
                action,
                codeValue: digits.join(''),
                url: String(location.href || ''),
              };
            })(arguments[0], arguments[1]);
            """,
            str(code or ""),
            bool(submit),
        )
    except Exception:
        payload = None
    return payload if isinstance(payload, dict) else None


def try_native_click_consent_continue(driver) -> dict[str, Any] | None:
    return try_native_click_button_by_patterns(
        driver,
        patterns=[r"continue", r"agree", r"allow", r"authorize"],
    )


def try_native_click_button_by_patterns(driver, *, patterns: list[str]) -> dict[str, Any] | None:
    try:
        payload = driver.execute_script(
            """
            return (function(patterns){
              const visible = (el) => {
                if (!el) return false;
                const st = window.getComputedStyle(el);
                return !!(st && st.display !== 'none' && st.visibility !== 'hidden' && el.offsetParent !== null);
              };
              const textOf = (el) => ((el.innerText || el.textContent || '').trim());
              const nodes = Array.from(document.querySelectorAll('button,[role="button"],a'));
              const regexes = (patterns || []).map((item) => {
                try {
                  return new RegExp(String(item), 'i');
                } catch (_) {
                  return null;
                }
              }).filter(Boolean);
              for (const node of nodes) {
                if (!visible(node)) continue;
                const txt = textOf(node);
                if (!txt) continue;
                if (regexes.length > 0 && !regexes.some((re) => re.test(txt))) continue;
                try {
                  node.click();
                  return {
                    ok: true,
                    action: 'click_button',
                    buttonText: txt.slice(0, 120),
                    url: String(location.href || ''),
                  };
                } catch (e) {}
              }
              return { ok: false, action: 'not-found', url: String(location.href || '') };
            })(arguments[0]);
            """,
            patterns,
        )
    except Exception:
        payload = None
    return payload if isinstance(payload, dict) else None


def inspect_callback_state_on_driver(driver, *, callback_url_contains: str = "localhost:1455") -> dict[str, Any] | None:
    try:
        payload = driver.execute_script(
            """
            return (function(expectedNeedle){
              const url = String(location.href || '');
              const body = String((document.body && document.body.innerText) || '').replace(/\\s+/g, ' ').trim().slice(0, 800);
              return {
                url,
                callbackMatched: expectedNeedle ? url.includes(expectedNeedle) : false,
                onConsentPage: /sign-in-with-chatgpt\\/codex\\/consent/i.test(url),
                challengePresent: /turnstile|verify you are human|just a moment|performing security verification|challenge/i.test(body),
                bodyExcerpt: body,
              };
            })(arguments[0]);
            """,
            str(callback_url_contains or ""),
        )
    except Exception:
        payload = None
    return payload if isinstance(payload, dict) else None


def wait_native_code_or_callback(
    driver,
    *,
    timeout_seconds: int = 60,
    callback_url_contains: str = "localhost:1455",
    try_solve_challenge_fn=None,
) -> dict[str, Any]:
    deadline = time.time() + max(5, int(timeout_seconds))
    last_surface = None
    last_callback = None
    while time.time() < deadline:
        callback_state = inspect_callback_state_on_driver(driver, callback_url_contains=callback_url_contains)
        if isinstance(callback_state, dict):
            last_callback = callback_state
            if callback_state.get("callbackMatched"):
                return {
                    "kind": "callback",
                    "callback": callback_state,
                }
            if callback_state.get("onConsentPage"):
                consent_result = try_native_click_consent_continue(driver)
                if isinstance(consent_result, dict) and consent_result.get("ok"):
                    time.sleep(0.8)
                    continue

        surface = inspect_auth_surface_on_driver(driver)
        if isinstance(surface, dict):
            last_surface = surface
            stage = auth_surface_stage(surface)
            if stage == "code":
                return {
                    "kind": "code",
                    "surface": surface,
                }
            if auth_surface_has_challenge(surface) and callable(try_solve_challenge_fn):
                try:
                    solved = bool(try_solve_challenge_fn("native-code-or-callback"))
                except Exception:
                    solved = False
                if solved:
                    time.sleep(0.8)
                    continue
        time.sleep(0.4)

    return {
        "kind": "timeout",
        "surface": last_surface,
        "callback": last_callback,
    }


def wait_native_auth_stage(
    driver,
    *,
    target_stage: str,
    timeout_seconds: int = 40,
    try_solve_challenge_fn=None,
    continue_button_patterns: list[str] | None = None,
) -> dict[str, Any]:
    deadline = time.time() + max(5, int(timeout_seconds))
    last_surface = None
    while time.time() < deadline:
        surface = inspect_auth_surface_on_driver(driver)
        if isinstance(surface, dict):
            last_surface = surface
            stage = auth_surface_stage(surface)
            if stage == target_stage:
                return {
                    "ok": True,
                    "stage": stage,
                    "surface": surface,
                }
            if auth_surface_has_challenge(surface) and callable(try_solve_challenge_fn):
                try:
                    solved = bool(try_solve_challenge_fn(f"native-stage-{target_stage}"))
                except Exception:
                    solved = False
                if solved:
                    time.sleep(0.8)
                    continue
            if continue_button_patterns:
                click_result = try_native_click_button_by_patterns(driver, patterns=continue_button_patterns)
                if isinstance(click_result, dict) and click_result.get("ok"):
                    time.sleep(0.8)
                    continue
        time.sleep(0.4)
    return {
        "ok": False,
        "stage": auth_surface_stage(last_surface),
        "surface": last_surface,
    }


def wait_native_callback_with_consent(
    driver,
    *,
    timeout_seconds: int = 60,
    callback_url_contains: str = "localhost:1455",
    try_solve_challenge_fn=None,
) -> bool:
    deadline = time.time() + max(5, int(timeout_seconds))
    while time.time() < deadline:
        callback_state = inspect_callback_state_on_driver(driver, callback_url_contains=callback_url_contains)
        if isinstance(callback_state, dict):
            if callback_state.get("callbackMatched"):
                return True
            if callback_state.get("onConsentPage"):
                consent_result = try_native_click_consent_continue(driver)
                if isinstance(consent_result, dict) and consent_result.get("ok"):
                    time.sleep(0.8)
                    continue
            if callback_state.get("challengePresent") and callable(try_solve_challenge_fn):
                try:
                    solved = bool(try_solve_challenge_fn("native-callback"))
                except Exception:
                    solved = False
                if solved:
                    time.sleep(0.8)
                    continue
        time.sleep(0.4)
    return False


def inspect_register_progress_on_driver(
    driver,
    *,
    callback_url_contains: str = "chatgpt.com/api/auth/callback/openai",
) -> dict[str, Any] | None:
    try:
        payload = driver.execute_script(
            """
            return (function(expectedNeedle){
              const url = String(location.href || '');
              const body = String((document.body && document.body.innerText) || '').replace(/\\s+/g, ' ').trim().slice(0, 1200);
              const has = (sel) => {
                const node = document.querySelector(sel);
                if (!node) return false;
                const st = window.getComputedStyle(node);
                return !!(st && st.display !== 'none' && st.visibility !== 'hidden' && node.offsetParent !== null);
              };
              return {
                url,
                callbackMatched: expectedNeedle ? url.includes(expectedNeedle) : false,
                onConsentPage: /sign-in-with-chatgpt\\/codex\\/consent/i.test(url),
                onAboutYouPage: /auth\\.openai\\.com\\/about-you/i.test(url),
                formActionAboutYou: has('form[action="/about-you"]'),
                birthdayGroupVisible: has('div[role="group"][id$="-birthday"]'),
                hiddenBirthdayVisible: has('input[type="hidden"][name="birthday"]'),
                nameInputVisible: has('input[name="name"], input[id*="name" i]'),
                leftEmailVerification: /auth\\.openai\\.com/i.test(url) && !/email-verification/i.test(url),
                otpRejected: /incorrect code|invalid code|wrong code|code incorrect|max_check_attempts/i.test(body),
                challengePresent: /turnstile|verify you are human|just a moment|performing security verification|challenge/i.test(body),
                bodyExcerpt: body,
              };
            })(arguments[0]);
            """,
            str(callback_url_contains or ""),
        )
    except Exception:
        payload = None
    return payload if isinstance(payload, dict) else None


def inspect_about_you_surface_on_driver(driver) -> dict[str, Any] | None:
    try:
        payload = driver.execute_script(
            """
            return (function(){
              const visible = (el) => {
                if (!el) return false;
                const st = window.getComputedStyle(el);
                return !!(st && st.display !== 'none' && st.visibility !== 'hidden' && el.offsetParent !== null);
              };
              const textOf = (el) => ((el.innerText || el.textContent || '').trim());
              const form = document.querySelector('form[action="/about-you"]');
              const group = form ? form.querySelector('div[role="group"][id$="-birthday"]') : null;
              const segText = (type) => {
                const node = group ? group.querySelector('div[contenteditable="true"][data-type="' + type + '"]') : null;
                return node ? textOf(node) : '';
              };
              const body = String((document.body && document.body.innerText) || '').replace(/\\s+/g, ' ').trim().slice(0, 1200);
              const buttons = Array.from(document.querySelectorAll('button,[role="button"],input[type="submit"]'))
                .filter(visible)
                .map((node) => textOf(node) || String(node.getAttribute('value') || ''))
                .filter(Boolean)
                .slice(0, 12);
              const nameInput = form ? form.querySelector('input[name="name"], input[autocomplete="name"], input[placeholder*="name" i]') : null;
              const hiddenBirthday = form ? form.querySelector('input[type="hidden"][name="birthday"]') : null;
              return {
                url: String(location.href || ''),
                onAboutYouPage: /auth\\.openai\\.com\\/about-you/i.test(String(location.href || '')),
                formPresent: !!form,
                nameInputVisible: !!(nameInput && visible(nameInput) && !nameInput.disabled),
                nameValue: nameInput ? String(nameInput.value || '') : '',
                birthdayGroupVisible: !!(group && visible(group)),
                monthText: segText('month'),
                dayText: segText('day'),
                yearText: segText('year'),
                hiddenBirthday: hiddenBirthday ? String(hiddenBirthday.value || '') : '',
                continueButtonTexts: buttons,
                challengePresent: /turnstile|verify you are human|just a moment|performing security verification|challenge/i.test(body),
                termsBlocked: /terms of use/i.test(body) && /(can't create your account|cannot create your account)/i.test(body),
                bodyExcerpt: body,
              };
            })();
            """
        )
    except Exception:
        payload = None
    return payload if isinstance(payload, dict) else None


def try_native_fill_about_you_name(driver, full_name: str) -> dict[str, Any] | None:
    try:
        payload = driver.execute_script(
            """
            return (function(expectedName){
              const visible = (el) => {
                if (!el) return false;
                const st = window.getComputedStyle(el);
                return !!(st && st.display !== 'none' && st.visibility !== 'hidden' && el.offsetParent !== null);
              };
              const form = document.querySelector('form[action="/about-you"]');
              if (!form) return { ok: false, reason: 'no_form', url: String(location.href || '') };
              const input = form.querySelector('input[name="name"], input[autocomplete="name"], input[placeholder*="name" i]');
              if (!input || !visible(input) || input.disabled) {
                return { ok: false, reason: 'no_name_input', url: String(location.href || '') };
              }
              const proto = (input.tagName || '').toLowerCase() === 'textarea'
                ? window.HTMLTextAreaElement.prototype
                : window.HTMLInputElement.prototype;
              const nativeSetter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
              try { input.focus(); } catch (e) {}
              if (typeof nativeSetter === 'function') {
                nativeSetter.call(input, expectedName);
              } else {
                input.value = expectedName;
              }
              input.dispatchEvent(new Event('input', { bubbles: true }));
              input.dispatchEvent(new Event('change', { bubbles: true }));
              try { input.dispatchEvent(new FocusEvent('blur', { bubbles: true })); } catch (e) {}
              try { input.blur(); } catch (e) {}
              return {
                ok: String(input.value || '') === String(expectedName || ''),
                value: String(input.value || ''),
                url: String(location.href || ''),
              };
            })(arguments[0]);
            """,
            str(full_name or ""),
        )
    except Exception:
        payload = None
    return payload if isinstance(payload, dict) else None


def try_native_fill_about_you_birthday(driver, iso_yyyy_mm_dd: str) -> dict[str, Any] | None:
    try:
        payload = driver.execute_script(
            """
            return (function(iso){
              const visible = (el) => {
                if (!el) return false;
                const st = window.getComputedStyle(el);
                return !!(st && st.display !== 'none' && st.visibility !== 'hidden' && el.offsetParent !== null);
              };
              const form = document.querySelector('form[action="/about-you"]');
              if (!form) return { ok: false, reason: 'no_form', url: String(location.href || '') };
              const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(iso || ''));
              if (!m) return { ok: false, reason: 'bad_iso', url: String(location.href || '') };
              const [, yyyy, mm, dd] = m;
              const monthNames = {
                '01': 'January', '02': 'February', '03': 'March', '04': 'April',
                '05': 'May', '06': 'June', '07': 'July', '08': 'August',
                '09': 'September', '10': 'October', '11': 'November', '12': 'December'
              };
              const group = form.querySelector('div[role="group"][id$="-birthday"]');
              if (!group || !visible(group)) return { ok: false, reason: 'no_group', url: String(location.href || '') };
              const setSeg = (type, text, ariaNow, ariaText) => {
                const el = group.querySelector('div[contenteditable="true"][data-type="' + type + '"]');
                if (!el) return '';
                try { el.focus(); } catch (e) {}
                try { el.textContent = text; } catch (e) {}
                if (ariaNow != null) {
                  try { el.setAttribute('aria-valuenow', String(ariaNow)); } catch (e) {}
                }
                if (ariaText) {
                  try { el.setAttribute('aria-valuetext', ariaText); } catch (e) {}
                }
                try { el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: text })); } catch (e) {}
                try { el.dispatchEvent(new Event('change', { bubbles: true })); } catch (e) {}
                try { el.dispatchEvent(new FocusEvent('blur', { bubbles: true })); } catch (e) {}
                try { el.blur(); } catch (e) {}
                return String((el.innerText || el.textContent || '').trim());
              };
              let hidden = form.querySelector('input[type="hidden"][name="birthday"]');
              if (!hidden) {
                hidden = document.createElement('input');
                hidden.type = 'hidden';
                hidden.name = 'birthday';
                form.appendChild(hidden);
              }
              try { hidden.value = iso; } catch (e) {}
              try { hidden.setAttribute('value', iso); } catch (e) {}
              try { hidden.dispatchEvent(new Event('input', { bubbles: true })); } catch (e) {}
              try { hidden.dispatchEvent(new Event('change', { bubbles: true })); } catch (e) {}
              const monthText = setSeg('month', mm, parseInt(mm, 10), mm + ' - ' + (monthNames[mm] || mm));
              const dayText = setSeg('day', dd, parseInt(dd, 10), dd);
              const yearText = setSeg('year', yyyy, parseInt(yyyy, 10), yyyy);
              return {
                ok: String(hidden.value || '') === iso,
                hidden: String(hidden.value || ''),
                monthText,
                dayText,
                yearText,
                url: String(location.href || ''),
              };
            })(arguments[0]);
            """,
            str(iso_yyyy_mm_dd or ""),
        )
    except Exception:
        payload = None
    return payload if isinstance(payload, dict) else None


def try_native_submit_about_you(driver) -> dict[str, Any] | None:
    try:
        payload = driver.execute_script(
            """
            return (function(){
              const visible = (el) => {
                if (!el) return false;
                const st = window.getComputedStyle(el);
                return !!(st && st.display !== 'none' && st.visibility !== 'hidden' && el.offsetParent !== null);
              };
              const textOf = (el) => ((el.innerText || el.textContent || '').trim());
              const form = document.querySelector('form[action="/about-you"]');
              if (!form) return { ok: false, reason: 'no_form', url: String(location.href || '') };
              const selectors = [
                'button[type="submit"]:not([disabled])',
                'input[type="submit"]:not([disabled])',
                'button:not([disabled])',
                '[role="button"]'
              ];
              for (const sel of selectors) {
                const nodes = Array.from(form.querySelectorAll(sel));
                for (const node of nodes) {
                  if (!visible(node)) continue;
                  const txt = textOf(node) || String(node.getAttribute('value') || '');
                  if (txt && !/finish|continue|next|create account|submit/i.test(txt)) continue;
                  try {
                    node.click();
                    return { ok: true, action: 'click_button', buttonText: txt.slice(0, 120), url: String(location.href || '') };
                  } catch (e) {}
                }
              }
              try {
                if (typeof form.requestSubmit === 'function') {
                  form.requestSubmit();
                  return { ok: true, action: 'request_submit', url: String(location.href || '') };
                }
              } catch (e) {}
              try {
                form.submit();
                return { ok: true, action: 'form_submit', url: String(location.href || '') };
              } catch (e) {}
              return { ok: false, reason: 'submit_failed', url: String(location.href || '') };
            })();
            """
        )
    except Exception:
        payload = None
    return payload if isinstance(payload, dict) else None


def wait_native_about_you_advance(
    driver,
    *,
    timeout_seconds: int = 30,
    try_solve_challenge_fn=None,
) -> dict[str, Any]:
    deadline = time.time() + max(5, int(timeout_seconds))
    last_surface = None
    while time.time() < deadline:
        surface = inspect_about_you_surface_on_driver(driver)
        if isinstance(surface, dict):
            last_surface = surface
            if surface.get("termsBlocked"):
                return {
                    "ok": False,
                    "kind": "terms-blocked",
                    "surface": surface,
                }
            if surface.get("challengePresent") and callable(try_solve_challenge_fn):
                try:
                    solved = bool(try_solve_challenge_fn("native-about-you"))
                except Exception:
                    solved = False
                if solved:
                    time.sleep(0.8)
                    continue
            if not surface.get("onAboutYouPage") and not surface.get("formPresent"):
                return {
                    "ok": True,
                    "kind": "advanced",
                    "surface": surface,
                }
        else:
            return {
                "ok": True,
                "kind": "advanced",
                "surface": surface,
            }
        time.sleep(0.4)
    return {
        "ok": False,
        "kind": "timeout",
        "surface": last_surface,
    }


def wait_native_register_post_otp_progress(
    driver,
    *,
    timeout_seconds: int = 60,
    callback_url_contains: str = "chatgpt.com/api/auth/callback/openai",
    try_solve_challenge_fn=None,
) -> dict[str, Any]:
    deadline = time.time() + max(5, int(timeout_seconds))
    last_progress = None
    last_surface = None
    while time.time() < deadline:
        progress = inspect_register_progress_on_driver(
            driver,
            callback_url_contains=callback_url_contains,
        )
        if isinstance(progress, dict):
            last_progress = progress
            if progress.get("callbackMatched"):
                return {
                    "ok": True,
                    "kind": "callback",
                    "progress": progress,
                }
            if progress.get("onConsentPage"):
                consent_result = try_native_click_consent_continue(driver)
                if isinstance(consent_result, dict) and consent_result.get("ok"):
                    time.sleep(0.8)
                    continue
            if (
                progress.get("onAboutYouPage")
                or progress.get("formActionAboutYou")
                or progress.get("birthdayGroupVisible")
                or progress.get("hiddenBirthdayVisible")
                or progress.get("nameInputVisible")
            ):
                return {
                    "ok": True,
                    "kind": "about-you",
                    "progress": progress,
                }
            if progress.get("leftEmailVerification"):
                return {
                    "ok": True,
                    "kind": "advanced",
                    "progress": progress,
                }
            if progress.get("otpRejected"):
                return {
                    "ok": False,
                    "kind": "otp-rejected",
                    "progress": progress,
                }
            if progress.get("challengePresent") and callable(try_solve_challenge_fn):
                try:
                    solved = bool(try_solve_challenge_fn("native-register-post-otp"))
                except Exception:
                    solved = False
                if solved:
                    time.sleep(0.8)
                    continue

        surface = inspect_auth_surface_on_driver(driver)
        if isinstance(surface, dict):
            last_surface = surface
            if auth_surface_has_challenge(surface) and callable(try_solve_challenge_fn):
                try:
                    solved = bool(try_solve_challenge_fn("native-register-post-otp-surface"))
                except Exception:
                    solved = False
                if solved:
                    time.sleep(0.8)
                    continue
        time.sleep(0.4)

    return {
        "ok": False,
        "kind": "timeout",
        "progress": last_progress,
        "surface": last_surface,
    }


def run_native_repair_login_flow(
    driver,
    *,
    email: str,
    password: str,
    fetch_code_fn,
    try_solve_challenge_fn=None,
    callback_url_contains: str = "localhost:1455",
) -> dict[str, Any]:
    email_result = try_native_auth_fill_email(driver, str(email or ""), submit=True)
    if not isinstance(email_result, dict) or not email_result.get("ok"):
        raise RuntimeError("native repair flow could not submit email stage")

    password_stage = wait_native_auth_stage(
        driver,
        target_stage="password",
        timeout_seconds=45,
        try_solve_challenge_fn=try_solve_challenge_fn,
        continue_button_patterns=[r"continue with password", r"password", r"continue"],
    )
    if not password_stage.get("ok"):
        raise RuntimeError(f"native repair flow did not reach password stage: {password_stage}")

    password_result = try_native_auth_fill_password(driver, str(password or ""), submit=True)
    if not isinstance(password_result, dict) or not password_result.get("ok"):
        raise RuntimeError("native repair flow could not submit password stage")

    code_or_callback = wait_native_code_or_callback(
        driver,
        timeout_seconds=80,
        callback_url_contains=callback_url_contains,
        try_solve_challenge_fn=try_solve_challenge_fn,
    )
    if code_or_callback.get("kind") == "callback":
        callback_state = inspect_callback_state_on_driver(driver, callback_url_contains=callback_url_contains) or {}
        return {
            "callback_url": str(callback_state.get("url") or ""),
            "chosen_mailbox_ref": "",
            "mode": "callback-direct",
            "runner": "native-camoufox",
        }

    if code_or_callback.get("kind") != "code":
        raise RuntimeError(f"native repair flow did not reach code/callback stage: {code_or_callback}")

    code, chosen_mailbox_ref = fetch_code_fn()
    code_result = try_native_submit_code(driver, str(code or ""), submit=True)
    if not isinstance(code_result, dict) or not code_result.get("ok"):
        raise RuntimeError("native repair flow could not submit otp stage")

    if not wait_native_callback_with_consent(
        driver,
        timeout_seconds=80,
        callback_url_contains=callback_url_contains,
        try_solve_challenge_fn=try_solve_challenge_fn,
    ):
        raise RuntimeError("native repair flow callback wait timed out")

    callback_state = inspect_callback_state_on_driver(driver, callback_url_contains=callback_url_contains) or {}
    callback_url = str(callback_state.get("url") or "")
    if not callback_url:
        try:
            callback_url = str(getattr(driver, "current_url", "") or "")
        except Exception:
            callback_url = ""
    if callback_url_contains and callback_url_contains not in callback_url:
        raise RuntimeError(f"native repair flow callback url mismatch: {callback_url!r}")

    return {
        "callback_url": callback_url,
        "chosen_mailbox_ref": str(chosen_mailbox_ref or ""),
        "mode": "otp-callback",
        "runner": "native-camoufox",
    }


def run_native_register_auth_flow(
    driver,
    *,
    email: str,
    address_jwt: str,
    oauth: Any,
    password: str,
    fetch_code_fn,
    try_solve_challenge_fn=None,
    callback_url_contains: str = "chatgpt.com/api/auth/callback/openai",
) -> dict[str, Any]:
    surface = inspect_auth_surface_on_driver(driver)
    stage = auth_surface_stage(surface)

    if stage not in ("password", "code"):
        email_result = try_native_auth_fill_email(driver, str(email or ""), submit=True)
        if not isinstance(email_result, dict) or not email_result.get("ok"):
            raise RuntimeError("native register flow could not submit email stage")

    if stage != "code":
        password_stage = wait_native_auth_stage(
            driver,
            target_stage="password",
            timeout_seconds=50,
            try_solve_challenge_fn=try_solve_challenge_fn,
            continue_button_patterns=[r"create account", r"sign up", r"next", r"continue", r"password"],
        )
        if not password_stage.get("ok"):
            raise RuntimeError(f"native register flow did not reach password stage: {password_stage}")

        password_result = try_native_auth_fill_password(driver, str(password or ""), submit=True)
        if not isinstance(password_result, dict) or not password_result.get("ok"):
            raise RuntimeError("native register flow could not submit password stage")

    code_or_callback = wait_native_code_or_callback(
        driver,
        timeout_seconds=80,
        callback_url_contains=callback_url_contains,
        try_solve_challenge_fn=try_solve_challenge_fn,
    )
    if code_or_callback.get("kind") == "callback":
        raise RuntimeError(f"native register flow reached callback before otp stage: {code_or_callback}")
    if code_or_callback.get("kind") != "code":
        raise RuntimeError(f"native register flow did not reach code/callback stage: {code_or_callback}")

    code = fetch_code_fn()
    code_result = try_native_submit_code(driver, str(code or ""), submit=True)
    if not isinstance(code_result, dict) or not code_result.get("ok"):
        raise RuntimeError("native register flow could not submit otp stage")

    post_otp = wait_native_register_post_otp_progress(
        driver,
        timeout_seconds=80,
        callback_url_contains=callback_url_contains,
        try_solve_challenge_fn=try_solve_challenge_fn,
    )
    if not post_otp.get("ok"):
        raise RuntimeError(f"native register flow did not advance after otp: {post_otp}")

    return {
        "email": str(email or ""),
        "address_jwt": str(address_jwt or ""),
        "oauth": oauth,
        "pwd": str(password or ""),
        "mode": str(post_otp.get("kind") or "advanced"),
        "runner": "native-camoufox",
    }


def run_native_register_profile_flow(
    driver,
    *,
    full_name: str,
    birthdate: str,
    try_solve_challenge_fn=None,
) -> dict[str, Any]:
    surface = inspect_about_you_surface_on_driver(driver)
    if not isinstance(surface, dict) or not (surface.get("onAboutYouPage") or surface.get("formPresent")):
        return {
            "ok": True,
            "mode": "noop-no-about-you",
            "surface": surface,
        }
    if surface.get("termsBlocked"):
        raise RuntimeError("native about-you flow detected terms block")

    name_result = try_native_fill_about_you_name(driver, str(full_name or ""))
    if not isinstance(name_result, dict) or not name_result.get("ok"):
        raise RuntimeError(f"native about-you flow could not fill name: {name_result}")

    bday_result = try_native_fill_about_you_birthday(driver, str(birthdate or ""))
    if not isinstance(bday_result, dict) or not bday_result.get("ok"):
        raise RuntimeError(f"native about-you flow could not fill birthday: {bday_result}")

    submit_result = try_native_submit_about_you(driver)
    if not isinstance(submit_result, dict) or not submit_result.get("ok"):
        raise RuntimeError(f"native about-you flow could not submit form: {submit_result}")

    advanced = wait_native_about_you_advance(
        driver,
        timeout_seconds=35,
        try_solve_challenge_fn=try_solve_challenge_fn,
    )
    if not advanced.get("ok"):
        raise RuntimeError(f"native about-you flow did not advance: {advanced}")

    return {
        "ok": True,
        "mode": str(advanced.get("kind") or "advanced"),
        "runner": "native-camoufox",
        "surface": advanced.get("surface"),
        "name": name_result,
        "birthday": bday_result,
        "submit": submit_result,
    }
