from __future__ import annotations

import os
import time
from typing import Any, Callable

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select

from .camoufox_native import (
    inspect_about_you_surface_on_driver,
    run_native_register_profile_flow,
)


def prepare_register_profile(
    *,
    driver,
    generate_name: Callable[[], tuple[str, str]],
    enter_birthday: Callable[[Any], str],
    click_with_debug: Callable[..., Any],
    dbg: Callable[..., Any],
    dump_page_body: Callable[..., Any],
    fill_about_you_birthday_segments: Callable[..., dict | None],
    force_submit_about_you_form: Callable[..., dict | None],
) -> dict[str, Any]:
    first_name, last_name = generate_name()
    full_name_str = first_name + ' ' + last_name

    birthdate = '1995-01-15'
    explicit_form_detected = False
    bday_filled = False
    browser_backend = str(getattr(driver, "_neuro_browser_backend", "") or "").strip().lower()

    def _raise_if_terms_blocked() -> None:
        try:
            current_url = str(getattr(driver, 'current_url', '') or '').strip().lower()
        except Exception:
            current_url = ''
        if 'auth.openai.com/about-you' not in current_url:
            return

        try:
            title_text = str(
                driver.execute_script("return (document && document.title) ? document.title : '';")
                or ''
            ).lower()
        except Exception:
            title_text = ''

        try:
            body_text = str(
                driver.execute_script(
                    "return (document && document.body && document.body.innerText) ? document.body.innerText : '';"
                )
                or ''
            )
        except Exception:
            body_text = ''

        body_low = body_text.lower()
        blocked = (
            "we can't create your account due to our terms of use" in body_low
            or "we cannot create your account due to our terms of use" in body_low
            or ("terms of use" in body_low and "can't create your account" in body_low)
            or ("terms of use" in body_low and "cannot create your account" in body_low)
            or ("terms of use" in title_text and "can't create your account" in body_low)
        )
        if not blocked:
            return

        try:
            dump_page_body(
                driver=driver,
                kind='about_you_terms_blocked',
                message='terms_of_use_blocked',
            )
        except Exception:
            pass
        raise RuntimeError("Blocked: Terms of Use restriction on about-you page.")

    def _is_visible(el) -> bool:
        try:
            return el.is_displayed() and el.is_enabled()
        except Exception:
            return False

    def _attrs_text(el) -> str:
        parts: list[str] = []
        for k in ('id', 'name', 'placeholder', 'aria-label', 'autocomplete', 'type'):
            try:
                v = (el.get_attribute(k) or '').strip()
                if v:
                    parts.append(v)
            except Exception:
                pass
        return ' '.join(parts).lower()

    def _safe_focus(el) -> None:
        try:
            click_with_debug(driver, el, tag='safe_focus', note='focus input before typing')
            return
        except Exception:
            pass
        try:
            driver.execute_script('arguments[0].focus();', el)
        except Exception:
            pass

    def _safe_clear(el) -> None:
        _safe_focus(el)
        try:
            el.send_keys(Keys.CONTROL + 'a')
            el.send_keys(Keys.BACKSPACE)
        except Exception:
            pass

    def _set_value_js(el, value: str) -> bool:
        try:
            return bool(
                driver.execute_script(
                    """
                    const el = arguments[0];
                    const value = arguments[1];
                    try { el.focus(); } catch (e) {}
                    try { el.value = value; } catch (e) { return false; }
                    try { el.dispatchEvent(new Event('input', { bubbles: true })); } catch (e) {}
                    try { el.dispatchEvent(new Event('change', { bubbles: true })); } catch (e) {}
                    return true;
                    """,
                    el,
                    value,
                )
            )
        except Exception:
            return False

    def _capture_about_you_snapshot() -> dict[str, Any] | None:
        try:
            return driver.execute_script(
                """
                return (function(){
                  const form = document.querySelector('form[action="/about-you"]');
                  const nameInp = form ? form.querySelector('input[name="name"]') : null;
                  const hiddenBirthday = form ? form.querySelector('input[type="hidden"][name="birthday"]') : null;
                  const group = form ? form.querySelector('div[role="group"][id$="-birthday"]') : null;
                  const readSeg = (type) => {
                    const el = group ? group.querySelector('div[contenteditable="true"][data-type="' + type + '"]') : null;
                    return el ? String((el.innerText || el.textContent || '').trim()) : '';
                  };
                  return {
                    ok: true,
                    url: String(location.href || ''),
                    nameValue: nameInp ? String(nameInp.value || '') : '',
                    hiddenBirthday: hiddenBirthday ? String(hiddenBirthday.value || '') : '',
                    monthText: readSeg('month'),
                    dayText: readSeg('day'),
                    yearText: readSeg('year'),
                    body: String((document.body && document.body.innerText) || '').slice(0, 800),
                  };
                })();
                """
            )
        except Exception:
            return None

    def _pick_best(elements, keywords: list[str], *, forbid: list[str] | None = None):
        forbid = forbid or []
        best = None
        best_score = 0
        for el in elements:
            txt = _attrs_text(el)
            if any(bad in txt for bad in forbid):
                continue
            score = 0
            for kw in keywords:
                if kw in txt:
                    score += 2
            if score > best_score:
                best_score = score
                best = el
        return best

    if browser_backend == 'camoufox':
        try:
            native_surface = inspect_about_you_surface_on_driver(driver)
            if isinstance(native_surface, dict) and (
                native_surface.get('onAboutYouPage') or native_surface.get('formPresent')
            ):
                native_profile_state = run_native_register_profile_flow(
                    driver,
                    full_name=full_name_str,
                    birthdate=birthdate,
                    try_solve_challenge_fn=None,
                )
                dbg('about-you', f'native profile flow success result={native_profile_state}', driver=driver)
                try:
                    dump_page_body(
                        driver=driver,
                        kind='native_about_you_flow_success',
                        message=f"mode={native_profile_state.get('mode')}",
                    )
                except Exception:
                    pass
                profile_result = {
                    'first_name': first_name,
                    'last_name': last_name,
                    'full_name_str': full_name_str,
                    'birthdate': birthdate,
                    'explicit_form_detected': True,
                    'bday_filled': True,
                    'native_mode': str(native_profile_state.get('mode') or ''),
                    'runner': str(native_profile_state.get('runner') or 'native-camoufox'),
                }
                try:
                    setattr(driver, "_neuro_register_profile_result", profile_result)
                except Exception:
                    pass
                return profile_result
        except Exception as exc:
            dbg('about-you', f'native profile flow fallback: {exc}', driver=driver)
            try:
                dump_page_body(
                    driver=driver,
                    kind='native_about_you_flow_fallback',
                    message=str(exc),
                )
            except Exception:
                pass

    try:
        t_end = time.time() + 20
        while time.time() < t_end:
            if driver.find_elements(By.CSS_SELECTOR, 'input, select'):
                break
            time.sleep(0.5)

        inputs = [el for el in driver.find_elements(By.CSS_SELECTOR, 'input') if _is_visible(el)]
        selects = [el for el in driver.find_elements(By.CSS_SELECTOR, 'select') if _is_visible(el)]

        forbid_name = ['email', 'password', 'code', 'otp', 'verification', 'phone']

        first_input = _pick_best(inputs, ['first', 'given'], forbid=forbid_name)
        last_input = _pick_best(inputs, ['last', 'family', 'surname'], forbid=forbid_name)
        full_name_input = _pick_best(inputs, ['full name', 'fullname'], forbid=forbid_name) or _pick_best(inputs, ['name'], forbid=forbid_name)

        name_filled = False
        if first_input and last_input:
            _safe_clear(first_input)
            first_input.send_keys(first_name)
            _safe_clear(last_input)
            last_input.send_keys(last_name)
            name_filled = True
        elif full_name_input:
            _safe_clear(full_name_input)
            full_name_input.send_keys(full_name_str)
            name_filled = True

        yyyy, mm, dd = birthdate.split('-')
        forbid_bday = ['email', 'password', 'code', 'otp']

        bday_input = _pick_best(inputs, ['birth', 'birthday', 'date of birth', 'dob', 'birthdate'], forbid=forbid_bday)
        month_sel = _pick_best(selects, ['month'], forbid=forbid_bday)
        day_sel = _pick_best(selects, ['day'], forbid=forbid_bday)
        year_sel = _pick_best(selects, ['year'], forbid=forbid_bday)

        def _ph(el) -> str:
            try:
                return (el.get_attribute('placeholder') or '').strip().lower()
            except Exception:
                return ''

        month_inp = next((el for el in inputs if _ph(el) in ('mm', 'month')), None)
        day_inp = next((el for el in inputs if _ph(el) in ('dd', 'day')), None)
        year_inp = next((el for el in inputs if _ph(el) in ('yyyy', 'year')), None)

        bday_filled = False
        if month_sel and day_sel and year_sel:
            try:
                Select(month_sel).select_by_value(str(int(mm)))
            except Exception:
                try:
                    Select(month_sel).select_by_visible_text(str(int(mm)))
                except Exception:
                    pass
            try:
                Select(day_sel).select_by_value(str(int(dd)))
            except Exception:
                try:
                    Select(day_sel).select_by_visible_text(str(int(dd)))
                except Exception:
                    pass
            try:
                Select(year_sel).select_by_value(yyyy)
            except Exception:
                try:
                    Select(year_sel).select_by_visible_text(yyyy)
                except Exception:
                    pass
            bday_filled = True
        elif month_inp and day_inp and year_inp:
            _safe_clear(month_inp)
            month_inp.send_keys(f'{int(mm):02d}')
            _safe_clear(day_inp)
            day_inp.send_keys(f'{int(dd):02d}')
            _safe_clear(year_inp)
            year_inp.send_keys(yyyy)
            bday_filled = True
        elif bday_input:
            btype = (bday_input.get_attribute('type') or '').strip().lower()
            if btype == 'date':
                if not _set_value_js(bday_input, birthdate):
                    _safe_clear(bday_input)
                    bday_input.send_keys(birthdate)
            else:
                masked = f'{int(mm):02d}/{int(dd):02d}/{yyyy}'
                _safe_clear(bday_input)
                for ch in f'{int(mm):02d}{int(dd):02d}{yyyy}':
                    bday_input.send_keys(ch)
                    time.sleep(0.03)
                _set_value_js(bday_input, masked)
            bday_filled = True
        else:
            try:
                if driver.find_elements(By.CSS_SELECTOR, 'input[type="hidden"][name="birthday"]'):
                    r = fill_about_you_birthday_segments(iso_yyyy_mm_dd=birthdate)
                    dbg('about-you', f'fill birthday segments result={r}', driver=driver)
                    bday_filled = bool(r and r.get('hidden') == birthdate)
            except Exception:
                pass

        explicit_form_detected = bool(name_filled or bday_filled)

        try:
            driver.switch_to.active_element.send_keys(Keys.TAB)
        except Exception:
            pass

    except Exception:
        pass

    if not bday_filled:
        try:
            if 'auth.openai.com/about-you' in str(getattr(driver, 'current_url', '') or ''):
                r = fill_about_you_birthday_segments(iso_yyyy_mm_dd=birthdate)
                dbg('about-you', f'post-fill birthday segments result={r}', driver=driver)
                bday_filled = bool(r and r.get('hidden') == birthdate)
        except Exception:
            pass

    if not explicit_form_detected and not bday_filled:
        birthdate = enter_birthday(driver)

    _raise_if_terms_blocked()
    try:
        u0 = str(getattr(driver, 'current_url', '') or '')
        if 'auth.openai.com/about-you' in u0 or driver.find_elements(By.CSS_SELECTOR, 'form[action="/about-you"]'):
            try:
                name_input = next(
                    (
                        el for el in driver.find_elements(By.CSS_SELECTOR, 'input[name="name"], input[autocomplete="name"], input[placeholder*="name" i]')
                        if _is_visible(el)
                    ),
                    None,
                )
            except Exception:
                name_input = None
            if name_input is not None:
                try:
                    current_name = str(name_input.get_attribute('value') or '')
                except Exception:
                    current_name = ''
                if current_name.strip() != full_name_str:
                    try:
                        _safe_clear(name_input)
                    except Exception:
                        pass
                    if not _set_value_js(name_input, full_name_str):
                        try:
                            name_input.send_keys(full_name_str)
                        except Exception:
                            pass
            try:
                snap = _capture_about_you_snapshot()
                if snap is not None:
                    dbg('about-you', f'pre-submit snapshot={snap}', driver=driver)
            except Exception:
                pass
            submit_mode = str(os.environ.get('ABOUT_YOU_SUBMIT_MODE', 'force') or 'force').strip().lower()
            if submit_mode in ('click', 'click_then_force'):
                try:
                    native_submit = None
                    native_xpaths = [
                        "//button[normalize-space(.)='Finish creating account']",
                        "//button[contains(normalize-space(.), 'Finish creating account')]",
                        "//button[@type='submit']",
                        "//input[@type='submit']",
                    ]
                    for xpath in native_xpaths:
                        try:
                            candidates = driver.find_elements(By.XPATH, xpath)
                        except Exception:
                            candidates = []
                        for candidate in candidates:
                            if _is_visible(candidate):
                                native_submit = candidate
                                break
                        if native_submit is not None:
                            break
                    if native_submit is not None:
                        click_with_debug(driver, native_submit, tag='about_you_native_submit', note='native click finish creating account')
                        dbg('about-you', 'clicked native finish creating account', driver=driver)
                        time.sleep(2)
                        try:
                            dump_page_body(driver=driver, kind='about_you_native_submit', message='native_finish_clicked')
                        except Exception:
                            pass
                        _raise_if_terms_blocked()
                        u1 = str(getattr(driver, 'current_url', '') or '')
                        if 'auth.openai.com/about-you' not in u1:
                            profile_result = {
                                'first_name': first_name,
                                'last_name': last_name,
                                'full_name_str': full_name_str,
                                'birthdate': birthdate,
                                'explicit_form_detected': explicit_form_detected,
                                'bday_filled': bday_filled,
                                'native_mode': 'legacy-fallback',
                                'runner': 'selenium-fallback' if browser_backend == 'camoufox' else 'selenium',
                            }
                            try:
                                setattr(driver, "_neuro_register_profile_result", profile_result)
                            except Exception:
                                pass
                            return profile_result
                    else:
                        dbg('about-you', 'native finish creating account button not found', driver=driver)
                except RuntimeError:
                    raise
                except Exception:
                    pass
                if submit_mode == 'click':
                    profile_result = {
                        'first_name': first_name,
                        'last_name': last_name,
                        'full_name_str': full_name_str,
                        'birthdate': birthdate,
                        'explicit_form_detected': explicit_form_detected,
                        'bday_filled': bday_filled,
                        'native_mode': 'legacy-fallback',
                        'runner': 'selenium-fallback' if browser_backend == 'camoufox' else 'selenium',
                    }
                    try:
                        setattr(driver, "_neuro_register_profile_result", profile_result)
                    except Exception:
                        pass
                    return profile_result
            rsub = force_submit_about_you_form(full_name=full_name_str, iso_yyyy_mm_dd=birthdate)
            dbg('about-you', f'force submit about-you result={rsub}', driver=driver)
            try:
                time.sleep(1)
                dump_page_body(driver=driver, kind='about_you_force_submit', message=f'birthdate={birthdate} result={rsub}')
            except Exception:
                pass
            _raise_if_terms_blocked()
    except RuntimeError:
        raise
    except Exception:
        pass

    profile_result = {
        'first_name': first_name,
        'last_name': last_name,
        'full_name_str': full_name_str,
        'birthdate': birthdate,
        'explicit_form_detected': explicit_form_detected,
        'bday_filled': bday_filled,
        'native_mode': 'legacy-fallback',
        'runner': 'selenium-fallback' if browser_backend == 'camoufox' else 'selenium',
    }
    try:
        setattr(driver, "_neuro_register_profile_result", profile_result)
    except Exception:
        pass
    return profile_result
