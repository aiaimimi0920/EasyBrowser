from __future__ import annotations

import time
from typing import Any, Callable

from .captcha_service_client import solve_turnstile_token
from .inline_turnstile_solver import (
    camoufox_inline_preferred,
    describe_inline_camoufox_solver,
    solve_turnstile_token_inline,
)


def extract_turnstile_task(driver) -> dict[str, Any] | None:
    try:
        payload = driver.execute_script(
            """
            const byQuery = (selector) => {
              const node = document.querySelector(selector);
              if (!node) return null;
              return {
                sitekey: node.getAttribute('data-sitekey') || '',
                action: node.getAttribute('data-action') || '',
                cData: node.getAttribute('data-cdata') || node.getAttribute('data-cData') || '',
              };
            };

            const widget = byQuery('[data-sitekey]') || byQuery('.cf-turnstile');
            if (widget && widget.sitekey) {
              return {
                websiteURL: window.location.href,
                websiteKey: widget.sitekey,
                action: widget.action || '',
                cData: widget.cData || '',
              };
            }

            const iframe = document.querySelector('iframe[src*="challenges.cloudflare.com"]');
            if (iframe) {
              try {
                const src = new URL(iframe.src, window.location.href);
                let websiteKey = src.searchParams.get('sitekey') || '';
                if (!websiteKey) {
                  const pathSegments = src.pathname
                    .split('/')
                    .map((segment) => String(segment || '').trim())
                    .filter(Boolean);
                  websiteKey = pathSegments.find((segment) => /^0x[0-9A-Za-z_-]{10,}$/.test(segment)) || '';
                }
                if (websiteKey) {
                  return {
                    websiteURL: window.location.href,
                    websiteKey,
                    action: src.searchParams.get('action') || '',
                    cData: src.searchParams.get('cData') || src.searchParams.get('data') || '',
                  };
                }
              } catch (_) {}
            }

            return null;
            """
        )
    except Exception:
        payload = None

    return payload if isinstance(payload, dict) else None


def inject_turnstile_token(driver, *, token: str) -> bool:
    try:
        result = driver.execute_script(
            """
            const token = arguments[0];
            let applied = 0;
            const selectors = [
              'input[name="cf-turnstile-response"]',
              'textarea[name="cf-turnstile-response"]',
              'input[name="g-recaptcha-response"]',
              'textarea[name="g-recaptcha-response"]',
            ];
            for (const selector of selectors) {
              for (const node of document.querySelectorAll(selector)) {
                try {
                  node.value = token;
                  node.setAttribute('value', token);
                  node.dispatchEvent(new Event('input', { bubbles: true }));
                  node.dispatchEvent(new Event('change', { bubbles: true }));
                  applied += 1;
                } catch (_) {}
              }
            }

            const invokeCallbacks = (root, seen = new Set()) => {
              if (!root || typeof root !== 'object' || seen.has(root)) return 0;
              seen.add(root);
              let hits = 0;
              for (const value of Object.values(root)) {
                if (!value || typeof value !== 'object') continue;
                if (typeof value.callback === 'function') {
                  try {
                    value.callback(token);
                    hits += 1;
                  } catch (_) {}
                }
                hits += invokeCallbacks(value, seen);
              }
              return hits;
            };

            if (window.___turnstile_cfg) {
              applied += invokeCallbacks(window.___turnstile_cfg);
            }

            for (const node of document.querySelectorAll('[data-callback]')) {
              try {
                const callbackName = node.getAttribute('data-callback');
                const fn = callbackName && window[callbackName];
                if (typeof fn === 'function') {
                  fn(token);
                  applied += 1;
                }
              } catch (_) {}
            }

            for (const button of document.querySelectorAll('button[type="submit"], input[type="submit"]')) {
              try {
                const style = window.getComputedStyle(button);
                const visible = style && style.display !== 'none' && style.visibility !== 'hidden';
                if (visible && !button.disabled) {
                  button.click();
                  break;
                }
              } catch (_) {}
            }
            return applied > 0;
            """,
            token,
        )
    except Exception:
        result = False
    return bool(result)


def maybe_solve_turnstile_challenge(
    driver,
    *,
    provider_kind: str | None,
    browser_backend: str | None = None,
    proxy: str | None = None,
    dbg_fn: Callable[..., Any] | None = None,
) -> bool:
    resolved_provider = str(provider_kind or "").strip()
    resolved_backend = str(browser_backend or "").strip().lower()
    if not resolved_provider and resolved_backend == "camoufox":
        resolved_provider = "turnstile-solver-camoufox"
    if not resolved_provider:
        return False
    task = extract_turnstile_task(driver)
    if not task:
        if dbg_fn:
            dbg_fn("captcha", "turnstile provider configured but no sitekey detected", driver=driver)
        return False
    try:
        if dbg_fn:
            dbg_fn(
                "captcha",
                f"solving turnstile provider={resolved_provider} backend={resolved_backend or 'custom'} sitekey={str(task.get('websiteKey') or '')[:16]}...",
                driver=driver,
            )
        solution: dict[str, Any]
        inline_meta = describe_inline_camoufox_solver()
        should_try_inline_first = (
            resolved_provider == "turnstile-solver-camoufox"
            and inline_meta.get("enabled") is True
            and inline_meta.get("patchrightAvailable") is True
            and (camoufox_inline_preferred() or resolved_backend == "camoufox")
        )
        if should_try_inline_first:
            solution = solve_turnstile_token_inline(
                website_url=str(task.get("websiteURL") or ""),
                website_key=str(task.get("websiteKey") or ""),
                proxy=proxy,
                action=str(task.get("action") or "").strip() or None,
                c_data=str(task.get("cData") or "").strip() or None,
            )
        else:
            try:
                solution = solve_turnstile_token(
                    website_url=str(task.get("websiteURL") or ""),
                    website_key=str(task.get("websiteKey") or ""),
                    provider_kind=resolved_provider,
                    proxy=proxy,
                    action=str(task.get("action") or "").strip() or None,
                    c_data=str(task.get("cData") or "").strip() or None,
                )
            except Exception:
                if (
                    resolved_provider == "turnstile-solver-camoufox"
                    and inline_meta.get("enabled") is True
                    and inline_meta.get("patchrightAvailable") is True
                ):
                    solution = solve_turnstile_token_inline(
                        website_url=str(task.get("websiteURL") or ""),
                        website_key=str(task.get("websiteKey") or ""),
                        proxy=proxy,
                        action=str(task.get("action") or "").strip() or None,
                        c_data=str(task.get("cData") or "").strip() or None,
                    )
                else:
                    raise
        token = str(solution.get("token") or "").strip()
        if not token:
            return False
        injected = inject_turnstile_token(driver, token=token)
        if injected and dbg_fn:
            dbg_fn("captcha", f"turnstile token injected provider={resolved_provider}", driver=driver)
        if injected:
            time.sleep(2.0)
        return injected
    except Exception as exc:
        if dbg_fn:
            dbg_fn("captcha", f"turnstile solve failed provider={resolved_provider}: {exc}", driver=driver)
        return False
