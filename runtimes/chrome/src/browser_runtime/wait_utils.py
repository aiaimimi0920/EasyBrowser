from __future__ import annotations

import os
import time
from typing import Any, Callable

from selenium.webdriver.common.by import By


def smart_wait(
    driver,
    by,
    value,
    timeout=20,
    *,
    debug_kind: str = '',
    debug_message: str = '',
    dbg_fn: Callable[..., None],
    click_with_debug_fn: Callable[..., None],
    dump_page_body_fn: Callable[..., None],
    save_error_artifacts_fn: Callable[..., None],
    raise_if_browser_network_error_fn: Callable[..., None],
):
    """Wait for an element and fail fast on fatal/challenge pages."""
    _ = (dbg_fn, click_with_debug_fn, dump_page_body_fn, save_error_artifacts_fn)

    fatal_hints = [
        '糟糕',
        '出错了',
        'oops',
        'something went wrong',
        'an error occurred',
        'operation timed out',
    ]
    challenge_hints = [
        'verify you are human',
        'performing security verification',
        'just a moment',
        'cloudflare',
    ]
    challenge_source_hints = [
        'cdn-cgi/challenge-platform',
        '__cf$cv$params',
        'jsd/main.js',
        'cf-challenge',
        'turnstile',
        'challenges.cloudflare.com',
    ]

    end_time = time.time() + timeout
    wait_started_at = time.time()
    challenge_grace_seconds = float(os.environ.get('SMART_WAIT_CHALLENGE_GRACE_SECONDS', '0') or '0')
    while time.time() < end_time:
        try:
            raise_if_browser_network_error_fn(driver, stage=debug_kind or f'wait:{by}={value}')

            page_text = str(
                driver.execute_script(
                    "return document && document.body ? (document.body.innerText || '') : '';"
                )
                or ''
            ).lower()
            title_text = str(driver.execute_script("return (document && document.title) ? document.title : '';") or '').lower()
            cur_url = str(getattr(driver, 'current_url', '') or '').lower()
            joined = '\n'.join([title_text, page_text, cur_url])
            page_source = str(getattr(driver, 'page_source', '') or '').lower()

            if any(h in page_text for h in fatal_hints):
                raise RuntimeError('fatal ui error page detected (oops/error page), restart this round')

            challenge_text_hit = any(h in joined for h in challenge_hints)
            challenge_source_hit = any(h in page_source for h in challenge_source_hints)
            lower_kind = (debug_kind or '').lower()
            is_email_stage = 'email_input' in lower_kind
            is_password_stage = 'password_input' in lower_kind or 'password_continue' in lower_kind
            visible_form_controls = bool(driver.execute_script(
                """
                const nodes = Array.from(document.querySelectorAll('input, button, textarea, select, a[href]'));
                return nodes.some((node) => {
                  const st = window.getComputedStyle(node);
                  if (!st) return false;
                  const rect = node.getBoundingClientRect();
                  return st.display !== 'none' && st.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                });
                """
            ) or False)
            email_stage_challenge = is_email_stage and challenge_source_hit and not visible_form_controls
            password_stage_challenge = is_password_stage and (challenge_text_hit or challenge_source_hit) and not visible_form_controls
            challenge_detected = challenge_text_hit or email_stage_challenge or password_stage_challenge or (challenge_source_hit and not (is_email_stage or is_password_stage))

            if challenge_detected:
                if (time.time() - wait_started_at) < challenge_grace_seconds:
                    time.sleep(0.5)
                    continue
                if debug_kind and 'password' in debug_kind.lower():
                    raise RuntimeError('blocked challenge page before password step')
                raise RuntimeError('blocked challenge page')

            el = driver.find_element(by, value)
            if el.is_displayed() and el.is_enabled():
                return el
        except Exception as exc:
            if isinstance(exc, RuntimeError):
                raise
        time.sleep(0.5)

    if debug_kind:
        raise RuntimeError(debug_message or f'wait failed: {debug_kind}')
    raise RuntimeError(f"wait failed for {by}={value}")


def find_visible(driver, by, value):
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


def click_if_found(driver, xpath: str, *, click_with_debug_fn: Callable[..., None]) -> bool:
    try:
        el = find_visible(driver, By.XPATH, xpath)
        if not el:
            return False
        click_with_debug_fn(driver, el, tag='click_if_found', note=f'xpath={xpath[:120]}')
        return True
    except Exception:
        return False


def wait_for_any(*, timeout_seconds: int, predicates: list[Callable[[], Any]]) -> Any:
    end = time.time() + timeout_seconds
    last_exc: Exception | None = None
    while time.time() < end:
        for predicate in predicates:
            try:
                value = predicate()
                if value:
                    return value
            except Exception as exc:
                last_exc = exc
        time.sleep(0.4)
    raise RuntimeError(f'timeout waiting for condition: {last_exc}')
