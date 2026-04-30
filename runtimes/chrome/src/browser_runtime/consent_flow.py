from __future__ import annotations

import time
from typing import Any, Callable

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from .camoufox_native import (
    inspect_callback_state_on_driver,
    native_camoufox_enabled,
    try_native_click_consent_continue,
    wait_native_callback_with_consent,
)


def _is_camoufox_backend(*, driver) -> bool:
    try:
        return str(getattr(driver, "_neuro_browser_backend", "") or "").strip().lower() == "camoufox"
    except Exception:
        return False


def _set_native_callback_state(*, driver, callback_url_contains: str) -> dict[str, Any] | None:
    if not _is_camoufox_backend(driver=driver) or not native_camoufox_enabled():
        return None
    try:
        state = inspect_callback_state_on_driver(driver, callback_url_contains=callback_url_contains)
    except Exception:
        state = None
    try:
        setattr(driver, "_neuro_finalize_callback_state", state if isinstance(state, dict) else None)
    except Exception:
        pass
    return state if isinstance(state, dict) else None


def click_final_continue_if_present(
    *,
    driver,
    dbg_fn: Callable[..., Any],
    find_visible_fn: Callable[..., Any],
    click_with_debug_fn: Callable[..., Any],
) -> bool:
    try:
        current_url = str(getattr(driver, 'current_url', '') or '')
    except Exception:
        current_url = ''
    current_url_lower = current_url.lower()
    if 'auth.openai.com' not in current_url_lower:
        dbg_fn('ui', f'skip continue click outside auth flow: {current_url}', driver=driver)
        return False

    is_about_you = 'auth.openai.com/about-you' in current_url_lower

    if is_about_you:
        about_you_xpaths = [
            "//button[normalize-space(.)='Finish creating account']",
            "//button[contains(normalize-space(.), 'Finish creating account')]",
            "//button[contains(normalize-space(.), '创建账号') or contains(normalize-space(.), '完成创建') or contains(normalize-space(.), '完成注册')]",
        ]
        for xpath in about_you_xpaths:
            element = find_visible_fn(driver, By.XPATH, xpath)
            if not element:
                continue
            click_with_debug_fn(driver, element, tag='finish_creating_account_button', note=f'about-you xpath={xpath[:90]}')
            return True

    xpaths = []
    if _is_codex_consent_page(driver=driver):
        xpaths.extend([
            "//button[normalize-space(.)='??']",
            "//button[@type='submit' and normalize-space(.)='??']",
            "//button[contains(normalize-space(.), '??') and not(contains(normalize-space(.), '??'))]",
            "//button[contains(normalize-space(.), '????')]",
            "//button[contains(normalize-space(.), '?????')]",
        ])
    xpaths.extend([
        "//button[(contains(., 'Agree') or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'continue')) and not(contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'continue with'))]",
        "//button[contains(normalize-space(.), '\u540c\u610f') or contains(normalize-space(.), '\u5141\u8bb8') or contains(normalize-space(.), '\u6388\u6743')]",
    ])
    for xpath in xpaths:
        element = find_visible_fn(driver, By.XPATH, xpath)
        if not element:
            continue
        click_with_debug_fn(driver, element, tag='continue_button', note=f'final-continue xpath={xpath[:90]}')
        return True
    return False


def _is_codex_consent_page(*, driver) -> bool:
    try:
        current_url = str(getattr(driver, 'current_url', '') or '')
    except Exception:
        current_url = ''
    current_url_lower = current_url.lower()
    if 'auth.openai.com' in current_url_lower and (
        'consent' in current_url_lower or 'login-to-codex' in current_url_lower or 'sign-in-with-chatgpt/codex' in current_url_lower
    ):
        return True
    try:
        body_text = str(driver.execute_script("return document && document.body ? (document.body.innerText || '') : '';") or '')
    except Exception:
        body_text = ''
    body_low = body_text.lower()
    markers = [
        'chatgpt will provide codex',
        "codex won't receive your chat history",
        'codex will not receive your chat history',
        '?????',
        'chatgpt ?? codex',
        'codex ????????????',
        '???? codex ?',
    ]
    return ('codex' in body_low and 'chatgpt' in body_low and any(marker in body_low for marker in markers))


def maybe_recover_from_terms_page(
    *,
    driver,
    dbg_fn: Callable[..., Any],
    dump_page_body_fn: Callable[..., Any],
) -> None:
    try:
        handles = list(driver.window_handles or [])
    except Exception:
        handles = []

    try:
        if len(handles) > 1:
            best = None
            for handle in handles:
                try:
                    driver.switch_to.window(handle)
                    current_url = str(getattr(driver, 'current_url', '') or '')
                    if 'auth.openai.com' in current_url or 'localhost:1455' in current_url or 'chatgpt.com' in current_url:
                        best = handle
                        break
                except Exception:
                    continue
            if best:
                driver.switch_to.window(best)
    except Exception:
        pass

    try:
        current_url = str(getattr(driver, 'current_url', '') or '')
        if 'openai.com/policies' in current_url:
            dbg_fn('recover', f'landed on policies page: {current_url}', driver=driver)
            dump_page_body_fn(driver=driver, kind='policies_page', message=current_url)
            try:
                driver.back()
                time.sleep(1)
            except Exception:
                pass
    except Exception:
        pass


def maybe_click_consent_continue_once(
    *,
    driver,
    click_final_continue_if_present_fn: Callable[[], bool],
    dbg_fn: Callable[..., Any],
    find_visible_fn: Callable[..., Any],
    callback_url_contains: str = 'localhost:1455',
) -> bool:
    try:
        current_url = str(getattr(driver, 'current_url', '') or '')
    except Exception:
        current_url = ''
    current_url_lower = current_url.lower()

    if not _is_codex_consent_page(driver=driver) and (
        'auth.openai.com' not in current_url_lower
        or (
            'sign-in-with-chatgpt/codex/consent' not in current_url_lower
            and 'login-to-codex' not in current_url_lower
            and 'consent' not in current_url_lower
        )
    ):
        return False

    try:
        driver.switch_to.active_element.send_keys(Keys.ESCAPE)
    except Exception:
        pass

    if _is_camoufox_backend(driver=driver):
        try:
            native_result = try_native_click_consent_continue(driver)
            if isinstance(native_result, dict) and native_result.get("ok"):
                dbg_fn('consent', f"native camoufox consent click action={native_result.get('action')}", driver=driver)
                _set_native_callback_state(driver=driver, callback_url_contains=callback_url_contains)
                return True
        except Exception:
            pass

    try:
        if click_final_continue_if_present_fn():
            dbg_fn('consent', 'fallback click continue by _click_final_continue_if_present', driver=driver)
            return True
    except Exception:
        pass

    xpaths = [
        "//button[contains(normalize-space(.), '\u7ee7\u7eed')]",
        "//button[contains(normalize-space(.), '\u540c\u610f')]",
        "//button[contains(normalize-space(.), '\u5141\u8bb8')]",
        "//button[contains(normalize-space(.), 'Continue')]",
        "//button[contains(normalize-space(.), 'Agree')]",
        "//a[contains(normalize-space(.), '\u7ee7\u7eed')]",
        "//a[contains(normalize-space(.), 'Continue')]",
    ]
    for xpath in xpaths:
        try:
            element = find_visible_fn(driver, By.XPATH, xpath)
            if not element:
                continue
            try:
                element.click()
            except Exception:
                driver.execute_script('arguments[0].click();', element)
            dbg_fn('consent', f'fallback js click continue xpath={xpath}', driver=driver)
            return True
        except Exception:
            continue
    return False


def _is_logged_in_chatgpt_web(*, driver) -> bool:
    try:
        current_url = str(getattr(driver, "current_url", "") or "").strip().lower()
    except Exception:
        current_url = ""

    if not current_url.startswith("https://chatgpt.com/"):
        return False
    if "/auth/" in current_url or "error=" in current_url:
        return False
    return True


def wait_for_callback_navigation(
    *,
    driver,
    maybe_recover_from_terms_page_fn: Callable[[], None],
    maybe_click_consent_continue_once_fn: Callable[[], bool],
    dump_page_body_fn: Callable[..., Any],
    save_error_artifacts_fn: Callable[..., Any],
    before_wait_check_fn: Callable[[], None] | None = None,
    retries: int = 6,
    wait_timeout: int = 12,
    callback_url_contains: str = 'localhost:1455',
) -> None:
    try:
        for _ in range(retries):
            maybe_recover_from_terms_page_fn()
            if before_wait_check_fn is not None:
                before_wait_check_fn()
            native_state = _set_native_callback_state(driver=driver, callback_url_contains=callback_url_contains)
            if isinstance(native_state, dict) and native_state.get("callbackMatched"):
                break
            maybe_click_consent_continue_once_fn()
            native_state = _set_native_callback_state(driver=driver, callback_url_contains=callback_url_contains)
            if isinstance(native_state, dict) and native_state.get("callbackMatched"):
                break
            if _is_camoufox_backend(driver=driver) and native_camoufox_enabled():
                try:
                    if wait_native_callback_with_consent(
                        driver,
                        timeout_seconds=max(3, int(wait_timeout)),
                        callback_url_contains=callback_url_contains,
                    ):
                        _set_native_callback_state(driver=driver, callback_url_contains=callback_url_contains)
                        break
                except Exception:
                    pass
            if _is_logged_in_chatgpt_web(driver=driver):
                raise RuntimeError("logged in chatgpt web without callback")
            try:
                WebDriverWait(driver, wait_timeout).until(EC.url_contains(callback_url_contains))
                _set_native_callback_state(driver=driver, callback_url_contains=callback_url_contains)
                break
            except TimeoutException:
                continue
        else:
            raise TimeoutException('callback not reached')
    except TimeoutException:
        target = callback_url_contains or 'callback target'
        try:
            _set_native_callback_state(driver=driver, callback_url_contains=callback_url_contains)
            dump_page_body_fn(driver=driver, kind='callback_timeout', message=str(getattr(driver, 'current_url', '') or ''))
        except Exception:
            pass
        save_error_artifacts_fn(driver=driver, kind='callback', message=f'Timeout waiting for callback URL containing: {target}')
        raise RuntimeError(f'Blocked: Timeout waiting for callback URL containing: {target}.')
