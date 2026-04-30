from __future__ import annotations

import time

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys


MONTH_NAMES = {
    "01": "January",
    "02": "February",
    "03": "March",
    "04": "April",
    "05": "May",
    "06": "June",
    "07": "July",
    "08": "August",
    "09": "September",
    "10": "October",
    "11": "November",
    "12": "December",
}


def force_set_birthday_iso(driver, *, iso_yyyy_mm_dd: str) -> dict | None:
    """Force-set the react-aria DateField hidden input used by /about-you.

    NOTE: This can be overwritten by React because the hidden input is
    controlled by internal state. Prefer `fill_about_you_birthday_segments()`
    which simulates real user typing into the contenteditable segments.
    """

    js = r"""
    return (function(v){
      try {
        const inp = document.querySelector('input[type="hidden"][name="birthday"]');
        if (!inp) return {ok:false, reason:'no_hidden_birthday'};
        const prev = inp.value;
        inp.value = v;
        try { inp.setAttribute('value', v); } catch (e) {}
        try { inp.dispatchEvent(new Event('input', {bubbles:true})); } catch (e) {}
        try { inp.dispatchEvent(new Event('change', {bubbles:true})); } catch (e) {}

        const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(v || '');
        if (m) {
          const group = document.querySelector('div[role="group"][id$="-birthday"]');
          if (group) {
            const setSeg = (t, txt) => {
              const el = group.querySelector('div[data-type="' + t + '"][contenteditable="true"]');
              if (el) {
                try { el.textContent = txt; } catch (e) {}
                try { el.dispatchEvent(new Event('input', {bubbles:true})); } catch (e) {}
                try { el.dispatchEvent(new Event('change', {bubbles:true})); } catch (e) {}
              }
            };
            setSeg('month', m[2]);
            setSeg('day', m[3]);
            setSeg('year', m[1]);
          }
        }

        return {ok:true, prev:prev, now:inp.value};
      } catch (e) {
        return {ok:false, reason:String(e)};
      }
    })(arguments[0]);
    """

    try:
        return driver.execute_script(js, iso_yyyy_mm_dd)
    except Exception:
        return None


def fill_about_you_birthday_segments(driver, *, iso_yyyy_mm_dd: str) -> dict | None:
    """Fill /about-you birthday by typing into react-aria contenteditable segments.

    This is the only method we've observed that updates the hidden
    `input[name=birthday]` reliably.
    """

    try:
        yyyy, mm, dd = (iso_yyyy_mm_dd or '').split('-')
    except Exception:
        return None

    try:
        def _read_hidden_birthday() -> str:
            try:
                return str(
                    driver.execute_script(
                        "var el = document.querySelector('input[type=\"hidden\"][name=\"birthday\"]'); return el ? (el.value || '') : '';"
                    )
                    or ''
                )
            except Exception:
                return ''

        group = driver.find_element(By.CSS_SELECTOR, 'div[role="group"][id$="-birthday"]')
        seg_month = group.find_element(By.CSS_SELECTOR, 'div[contenteditable="true"][data-type="month"]')
        seg_day = group.find_element(By.CSS_SELECTOR, 'div[contenteditable="true"][data-type="day"]')
        seg_year = group.find_element(By.CSS_SELECTOR, 'div[contenteditable="true"][data-type="year"]')

        def _type_seg(el, text: str) -> str:
            try:
                driver.execute_script('arguments[0].scrollIntoView({block:"center"});', el)
            except Exception:
                pass
            try:
                el.click()
            except Exception:
                try:
                    driver.execute_script('arguments[0].focus();', el)
                except Exception:
                    pass

            try:
                driver.execute_script(
                    """
                    const el = arguments[0];
                    try { el.focus(); } catch (e) {}
                    try {
                      const selection = window.getSelection();
                      const range = document.createRange();
                      range.selectNodeContents(el);
                      selection.removeAllRanges();
                      selection.addRange(range);
                    } catch (e) {}
                    try { document.execCommand('delete', false); } catch (e) {}
                    try { el.textContent = ''; } catch (e) {}
                    """,
                    el,
                )
            except Exception:
                pass
            try:
                el.send_keys(Keys.CONTROL + 'a')
                el.send_keys(Keys.BACKSPACE)
                el.send_keys(Keys.DELETE)
            except Exception:
                pass
            for ch in text:
                el.send_keys(ch)
                time.sleep(0.02)
            try:
                return str(driver.execute_script('return (arguments[0].innerText || arguments[0].textContent || "").trim();', el) or '')
            except Exception:
                try:
                    return str((el.text or '').strip())
                except Exception:
                    return ''

        typed_month = _type_seg(seg_month, mm)
        typed_day = _type_seg(seg_day, dd)
        typed_year = _type_seg(seg_year, yyyy)

        month_name = MONTH_NAMES.get(mm, mm)

        normalized = driver.execute_script(
            """
            var group = arguments[0];
            var mm = arguments[1];
            var dd = arguments[2];
            var yyyy = arguments[3];
            var monthName = arguments[4];

            function parseNum(value) {
              var n = parseInt(String(value || '').replace(/\\D+/g, ''), 10);
              return Number.isFinite(n) ? n : null;
            }

            function setSeg(type, text, ariaNow, ariaText) {
              var el = group.querySelector('div[contenteditable="true"][data-type="' + type + '"]');
              if (!el) return null;
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
              return (el.innerText || el.textContent || '').trim();
            }

            var monthNow = parseNum(mm);
            var dayNow = parseNum(dd);
            var yearNow = parseNum(yyyy);
            var monthAriaText = monthNow != null ? (mm + ' - ' + monthName) : mm;

            var monthText = setSeg('month', mm, monthNow, monthAriaText);
            var dayText = setSeg('day', dd, dayNow, dd);
            var yearText = setSeg('year', yyyy, yearNow, yyyy);

            var hidden = document.querySelector('input[type="hidden"][name="birthday"]');
            if (hidden) {
              var iso = yyyy + '-' + mm + '-' + dd;
              try { hidden.value = iso; } catch (e) {}
              try { hidden.setAttribute('value', iso); } catch (e) {}
              try { hidden.dispatchEvent(new Event('input', { bubbles: true })); } catch (e) {}
              try { hidden.dispatchEvent(new Event('change', { bubbles: true })); } catch (e) {}
            }

            var describedBy = group.getAttribute('aria-describedby');
            if (describedBy) {
              var desc = document.getElementById(describedBy);
              if (desc) {
                var dayDisplay = parseNum(dd);
                if (dayDisplay == null) {
                  dayDisplay = dd;
                }
                try { desc.textContent = 'Selected Date: ' + monthName + ' ' + String(dayDisplay) + ', ' + yyyy; } catch (e) {}
              }
            }

            return {
              monthText,
              dayText,
              yearText,
              hidden: hidden ? (hidden.value || '') : '',
            };
            """,
            group,
            mm,
            dd,
            yyyy,
            month_name,
        )

        try:
            seg_year.send_keys(Keys.TAB)
        except Exception:
            pass

        hidden_now = _read_hidden_birthday()
        repair_attempts = 0
        repair_result = None
        while str(hidden_now or '') != iso_yyyy_mm_dd and repair_attempts < 2:
            repair_attempts += 1
            repair_result = force_set_birthday_iso(driver, iso_yyyy_mm_dd=iso_yyyy_mm_dd)
            time.sleep(0.08)
            normalized = driver.execute_script(
                """
                var group = arguments[0];
                var mm = arguments[1];
                var dd = arguments[2];
                var yyyy = arguments[3];
                var monthName = arguments[4];

                function parseNum(value) {
                  var n = parseInt(String(value || '').replace(/\\D+/g, ''), 10);
                  return Number.isFinite(n) ? n : null;
                }

                function setSeg(type, text, ariaNow, ariaText) {
                  var el = group.querySelector('div[contenteditable="true"][data-type="' + type + '"]');
                  if (!el) return null;
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
                  return (el.innerText || el.textContent || '').trim();
                }

                var monthNow = parseNum(mm);
                var dayNow = parseNum(dd);
                var yearNow = parseNum(yyyy);
                var monthAriaText = monthNow != null ? (mm + ' - ' + monthName) : mm;

                var monthText = setSeg('month', mm, monthNow, monthAriaText);
                var dayText = setSeg('day', dd, dayNow, dd);
                var yearText = setSeg('year', yyyy, yearNow, yyyy);

                var hidden = document.querySelector('input[type="hidden"][name="birthday"]');
                if (hidden) {
                  var iso = yyyy + '-' + mm + '-' + dd;
                  try { hidden.value = iso; } catch (e) {}
                  try { hidden.setAttribute('value', iso); } catch (e) {}
                  try { hidden.dispatchEvent(new Event('input', { bubbles: true })); } catch (e) {}
                  try { hidden.dispatchEvent(new Event('change', { bubbles: true })); } catch (e) {}
                }

                return {
                  monthText: monthText,
                  dayText: dayText,
                  yearText: yearText,
                  hidden: hidden ? (hidden.value || '') : ''
                };
                """,
                group,
                mm,
                dd,
                yyyy,
                month_name,
            )
            hidden_now = _read_hidden_birthday()

        if str(hidden_now or '') != iso_yyyy_mm_dd and repair_result and repair_result.get('ok'):
            try:
                force_set_birthday_iso(driver, iso_yyyy_mm_dd=iso_yyyy_mm_dd)
            except Exception:
                pass
            try:
                driver.execute_script(
                    """
                    var ae = document.activeElement;
                    if (ae && typeof ae.blur === 'function') {
                      try { ae.blur(); } catch (e) {}
                    }
                    var hidden = document.querySelector('input[type="hidden"][name="birthday"]');
                    if (hidden) {
                      var iso = arguments[0];
                      try { hidden.value = iso; } catch (e) {}
                      try { hidden.setAttribute('value', iso); } catch (e) {}
                    }
                    """,
                    iso_yyyy_mm_dd,
                )
            except Exception:
                pass
            hidden_now = iso_yyyy_mm_dd
            if isinstance(normalized, dict):
                normalized['hidden'] = iso_yyyy_mm_dd

        return {
            'ok': str(hidden_now or '') == iso_yyyy_mm_dd,
            'iso': iso_yyyy_mm_dd,
            'hidden': str(hidden_now or ''),
            'typedMonth': typed_month,
            'typedDay': typed_day,
            'typedYear': typed_year,
            'monthText': str((normalized or {}).get('monthText') or ''),
            'dayText': str((normalized or {}).get('dayText') or ''),
            'yearText': str((normalized or {}).get('yearText') or ''),
            'repairAttempts': repair_attempts,
            'repairResult': repair_result,
        }
    except Exception as e:
        return {'ok': False, 'reason': str(e)}


def force_submit_about_you_form(driver, *, full_name: str, iso_yyyy_mm_dd: str) -> dict | None:
    """Force-submit the /about-you form with a guaranteed birthday payload.

    We observed react-aria DateField can display our typed segments but still
    keeps the hidden `input[name=birthday]` at its default (TODAY), which the
    server rejects. This function removes the existing hidden birthday input
    and injects a new one right before submitting the form.
    """

    js = r"""
    return (function(nameV, bdayV){
      try {
        const form = document.querySelector('form[action="/about-you"]');
        if (!form) return {ok:false, reason:'no_form'};

        const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(bdayV || '');
        const monthNames = {
          '01': 'January', '02': 'February', '03': 'March', '04': 'April',
          '05': 'May', '06': 'June', '07': 'July', '08': 'August',
          '09': 'September', '10': 'October', '11': 'November', '12': 'December'
        };

        let nameFound = false;
        let nameValue = '';
        try {
          const nameInp = form.querySelector('input[name="name"]');
          if (nameInp) {
            nameFound = true;
            nameInp.value = nameV || '';
            try { nameInp.dispatchEvent(new Event('input', {bubbles:true})); } catch (e) {}
            try { nameInp.dispatchEvent(new Event('change', {bubbles:true})); } catch (e) {}
            try { nameValue = String(nameInp.value || ''); } catch (e) {}
          }
        } catch (e) {}

        let removed = 0;
        try {
          const olds = form.querySelectorAll('input[type="hidden"][name="birthday"]');
          removed = olds ? olds.length : 0;
          olds && olds.forEach(n => { try { n.remove(); } catch (e) {} });
        } catch (e) {}

        let hiddenBirthday = '';
        try {
          const inp = document.createElement('input');
          inp.type = 'hidden';
          inp.name = 'birthday';
          inp.value = bdayV || '';
          try { inp.setAttribute('value', bdayV || ''); } catch (e) {}
          form.appendChild(inp);
          hiddenBirthday = String(inp.value || '');
        } catch (e) {}

        if (match) {
          try {
            const [, yyyy, mm, dd] = match;
            const group = form.querySelector('div[role="group"][id$="-birthday"]');
            const setSeg = (type, text, ariaNow, ariaText) => {
              const el = group ? group.querySelector('div[contenteditable="true"][data-type="' + type + '"]') : null;
              if (!el) return null;
              try { el.textContent = text; } catch (e) {}
              if (ariaNow != null) {
                try { el.setAttribute('aria-valuenow', String(ariaNow)); } catch (e) {}
              }
              if (ariaText) {
                try { el.setAttribute('aria-valuetext', ariaText); } catch (e) {}
              }
              try { el.dispatchEvent(new InputEvent('input', { bubbles:true, inputType:'insertText', data:text })); } catch (e) {}
              try { el.dispatchEvent(new Event('change', { bubbles:true })); } catch (e) {}
              return (el.innerText || el.textContent || '').trim();
            };
            const monthName = monthNames[mm] || mm;
            setSeg('month', mm, parseInt(mm, 10), mm + ' – ' + monthName);
            setSeg('day', dd, parseInt(dd, 10), dd);
            setSeg('year', yyyy, parseInt(yyyy, 10), yyyy);
            if (group) {
              const describedBy = group.getAttribute('aria-describedby');
              if (describedBy) {
                const desc = document.getElementById(describedBy);
                if (desc) {
                  try { desc.textContent = 'Selected Date: ' + monthName + ' ' + String(parseInt(dd, 10)) + ', ' + yyyy; } catch (e) {}
                }
              }
            }
          } catch (e) {}
        }

        let consentValue = '';
        try {
          const c = form.querySelector('input[type="hidden"][name="isExplicitConsentRequired"]');
          if (!c) {
            const ci = document.createElement('input');
            ci.type = 'hidden';
            ci.name = 'isExplicitConsentRequired';
            ci.value = 'false';
            form.appendChild(ci);
            consentValue = 'false';
          } else {
            consentValue = String(c.value || '');
          }
        } catch (e) {}

        try {
          const btn = form.querySelector('button[type="submit"], input[type="submit"]');
          if (btn) {
            btn.click();
          } else {
            form.submit();
          }
        } catch (e) {
          return {ok:false, reason:'submit_failed:' + String(e), removed:removed};
        }
        return {
          ok:true,
          removed:removed,
          birthday:bdayV,
          hiddenBirthday:hiddenBirthday,
          nameFound:nameFound,
          nameValue:nameValue,
          consentValue:consentValue
        };
      } catch (e) {
        return {ok:false, reason:String(e)};
      }
    })(arguments[0], arguments[1]);
    """

    try:
        return driver.execute_script(js, full_name, iso_yyyy_mm_dd)
    except Exception:
        return None
