from __future__ import annotations

import asyncio
import os
import time
from typing import Any
from urllib.parse import unquote, urlparse

try:
    from patchright.async_api import async_playwright  # type: ignore
    _PATCHRIGHT_IMPORT_ERROR: str | None = None
except Exception as exc:  # pragma: no cover
    async_playwright = None  # type: ignore[assignment]
    _PATCHRIGHT_IMPORT_ERROR = str(exc)


def patchright_available() -> bool:
    return async_playwright is not None


def patchright_import_error() -> str | None:
    return _PATCHRIGHT_IMPORT_ERROR


def camoufox_inline_enabled() -> bool:
    return (os.environ.get("TURNSTILE_SOLVER_INLINE") or "1").strip().lower() not in ("0", "false", "no", "off")


def camoufox_inline_preferred() -> bool:
    return (os.environ.get("TURNSTILE_SOLVER_INLINE_PREFER") or "0").strip().lower() not in ("0", "false", "no", "off")


def describe_inline_camoufox_solver() -> dict[str, Any]:
    return {
        "enabled": camoufox_inline_enabled(),
        "preferred": camoufox_inline_preferred(),
        "patchrightAvailable": patchright_available(),
        "patchrightImportError": patchright_import_error(),
    }


def solve_turnstile_token_inline(
    *,
    website_url: str,
    website_key: str,
    proxy: str | None = None,
    action: str | None = None,
    c_data: str | None = None,
    user_agent: str | None = None,
) -> dict[str, Any]:
    if not camoufox_inline_enabled():
        raise RuntimeError("inline camoufox solver is disabled")
    if async_playwright is None:
        raise RuntimeError(f"patchright is unavailable: {_PATCHRIGHT_IMPORT_ERROR or 'not installed'}")
    return asyncio.run(
        _solve_once(
            website_url=website_url,
            website_key=website_key,
            proxy=proxy,
            action=action,
            c_data=c_data,
            user_agent=user_agent,
        )
    )


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
        return (os.environ.get("TURNSTILE_SOLVER_BLOCK_IMAGES") or "0").strip().lower() not in ("0", "false", "no", "off")
    if normalized == "stylesheet":
        return (os.environ.get("TURNSTILE_SOLVER_BLOCK_CSS") or "0").strip().lower() not in ("0", "false", "no", "off")
    if normalized == "font":
        return (os.environ.get("TURNSTILE_SOLVER_BLOCK_FONTS") or "0").strip().lower() not in ("0", "false", "no", "off")
    return False


async def _solve_once(
    *,
    website_url: str,
    website_key: str,
    proxy: str | None,
    action: str | None,
    c_data: str | None,
    user_agent: str | None,
) -> dict[str, Any]:
    proxy_settings = _proxy_settings(proxy)
    timeout_ms = max(5_000, int((os.environ.get("TURNSTILE_SOLVER_TIMEOUT_MS") or "90000").strip() or "90000"))
    headless = (os.environ.get("TURNSTILE_SOLVER_HEADLESS") or "1").strip().lower() not in ("0", "false", "no", "off")
    channel = (os.environ.get("TURNSTILE_SOLVER_BROWSER_TYPE") or "chrome").strip() or "chrome"
    viewport = {
        "width": int((os.environ.get("TURNSTILE_SOLVER_VIEWPORT_WIDTH") or "1365").strip() or "1365"),
        "height": int((os.environ.get("TURNSTILE_SOLVER_VIEWPORT_HEIGHT") or "1024").strip() or "1024"),
    }

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            channel=channel if channel != "camoufox" else "chrome",
            headless=headless,
            proxy=proxy_settings,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-popup-blocking",
                "--disable-renderer-backgrounding",
                "--disable-backgrounding-occluded-windows",
            ],
        )
        context = await browser.new_context(
            viewport=viewport,
            user_agent=user_agent or None,
            locale=(os.environ.get("TURNSTILE_SOLVER_LOCALE") or "en-US").strip() or "en-US",
            timezone_id=(os.environ.get("TURNSTILE_SOLVER_TIMEZONE_ID") or "UTC").strip() or "UTC",
            color_scheme="light",
        )
        page = await context.new_page()

        async def _route_handler(route) -> None:
            try:
                if _block_resource(str(route.request.resource_type or "")):
                    await route.abort()
                    return
            except Exception:
                pass
            await route.continue_()

        await page.route("**/*", _route_handler)
        await page.goto(website_url, wait_until="domcontentloaded", timeout=timeout_ms)
        await page.evaluate(
            """
            async ({ sitekey, action, cData }) => {
              if (!document.querySelector('script[src*="challenges.cloudflare.com/turnstile"]')) {
                const script = document.createElement('script');
                script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';
                script.async = true;
                document.head.appendChild(script);
                await new Promise((resolve) => {
                  script.onload = () => resolve(null);
                  script.onerror = () => resolve(null);
                });
              }
              let container = document.getElementById('__codex-inline-turnstile-overlay');
              if (!container) {
                container = document.createElement('div');
                container.id = '__codex-inline-turnstile-overlay';
                container.style.position = 'fixed';
                container.style.zIndex = '2147483647';
                container.style.top = '12px';
                container.style.right = '12px';
                container.style.background = 'rgba(255,255,255,0.92)';
                container.style.padding = '8px';
                container.style.borderRadius = '8px';
                container.style.boxShadow = '0 6px 18px rgba(0,0,0,0.16)';
                document.body.appendChild(container);
              }
              container.innerHTML = '';
              const widget = document.createElement('div');
              widget.className = 'cf-turnstile';
              widget.setAttribute('data-sitekey', sitekey);
              if (action) widget.setAttribute('data-action', action);
              if (cData) widget.setAttribute('data-cdata', cData);
              container.appendChild(widget);
              if (window.turnstile && typeof window.turnstile.render === 'function') {
                try {
                  window.turnstile.render(widget, {
                    sitekey,
                    action: action || undefined,
                    cData: cData || undefined,
                  });
                } catch (_) {}
              }
            }
            """,
            {"sitekey": website_key, "action": action, "cData": c_data},
        )

        deadline = time.time() + max(5.0, timeout_ms / 1000.0)
        token = ""
        while time.time() < deadline:
            for selector in (
                'input[name="cf-turnstile-response"]',
                'textarea[name="cf-turnstile-response"]',
                'input[name="g-recaptcha-response"]',
                'textarea[name="g-recaptcha-response"]',
            ):
                try:
                    token = str(await page.locator(selector).first.input_value(timeout=500) or "").strip()
                except Exception:
                    token = ""
                if token:
                    break
            if token:
                break
            try:
                token = str(await page.evaluate(
                    """
                    () => {
                      const cfg = window.___turnstile_cfg;
                      const stack = [cfg];
                      const seen = new Set();
                      while (stack.length > 0) {
                        const current = stack.pop();
                        if (!current || typeof current !== 'object' || seen.has(current)) continue;
                        seen.add(current);
                        for (const value of Object.values(current)) {
                          if (!value || typeof value !== 'object') continue;
                          if (typeof value.response === 'string' && value.response.trim()) {
                            return value.response.trim();
                          }
                          stack.push(value);
                        }
                      }
                      return '';
                    }
                    """
                ) or "").strip()
            except Exception:
                token = ""
            if token:
                break
            await page.wait_for_timeout(500)

        await context.close()
        await browser.close()

    if not token:
        raise RuntimeError("turnstile inline solver did not produce a token")

    now_ts = int(time.time())
    return {
        "token": token,
        "userAgent": user_agent or "",
        "cost": "0",
        "solveCount": 1,
        "createTime": now_ts,
        "endTime": now_ts,
        "provider": "turnstile-solver-camoufox-inline",
    }
