from __future__ import annotations

import re
from typing import Callable


def dbg(*, step: str, msg: str = "", driver=None, debug_trace: bool = False) -> None:
    _ = (step, msg, driver, debug_trace)


def dump_page_body(
    *,
    driver,
    kind: str,
    message: str = "",
    dump_page_body: bool,
    data_path_fn: Callable[..., str],
    error_dirname: str,
    instance_id: str,
    debug_trace: bool,
    keep_last_n_files_fn: Callable[..., None],
) -> None:
    _ = (
        driver,
        kind,
        message,
        dump_page_body,
        data_path_fn,
        error_dirname,
        instance_id,
        debug_trace,
        keep_last_n_files_fn,
    )


def save_error_artifacts(
    *,
    driver,
    kind: str,
    message: str = "",
    data_path_fn: Callable[..., str],
    error_dirname: str,
    instance_id: str,
    keep_last_n_files_fn: Callable[..., None],
) -> None:
    _ = (driver, kind, message, data_path_fn, error_dirname, instance_id, keep_last_n_files_fn)


def detect_browser_network_error(driver) -> tuple[str | None, str]:
    cur_url = ""
    title_text = ""
    body_text = ""
    page_source = ""
    try:
        cur_url = str(getattr(driver, "current_url", "") or "")
    except Exception:
        cur_url = ""
    try:
        title_text = str(getattr(driver, "title", "") or "")
    except Exception:
        title_text = ""
    try:
        body_text = str(
            driver.execute_script("return document && document.body ? (document.body.innerText || '') : ''; ") or ""
        )
    except Exception:
        body_text = ""
    try:
        page_source = str(getattr(driver, "page_source", "") or "")
    except Exception:
        page_source = ""

    joined_raw = "\n".join([cur_url, title_text, body_text, page_source])
    joined = joined_raw.lower()
    error_code = None
    match = re.search(r"\b(ERR_[A-Z0-9_]+)\b", joined_raw, flags=re.IGNORECASE)
    if match:
        error_code = str(match.group(1) or "").upper()

    strong_hints = (
        cur_url.lower().startswith("chrome-error://")
        or "chrome-error://chromewebdata" in joined
        or "this site can?t be reached" in joined
        or "this site can't be reached" in joined
        or "this page isn?t working" in joined
        or "this page isn't working" in joined
        or "refused to connect" in joined
        or '"errorcode":"err_' in joined
        or ("loadtimedataraw" in joined and "errorcode" in joined)
    )
    if not strong_hints and not error_code:
        return None, cur_url
    return error_code or "BROWSER_NETWORK_ERROR", cur_url


def raise_if_browser_network_error(
    driver,
    *,
    stage: str,
    detect_browser_network_error_fn: Callable[..., tuple[str | None, str]],
) -> None:
    code, cur_url = detect_browser_network_error_fn(driver)
    if code:
        raise RuntimeError(f"browser network error page detected: {code}; stage={stage}; url={cur_url}")


def click_with_debug(
    *,
    driver,
    el,
    tag: str,
    note: str = "",
    dbg_fn: Callable[..., None],
    dump_page_body_fn: Callable[..., None],
    raise_if_browser_network_error_fn: Callable[..., None],
) -> None:
    _ = (tag, note, dbg_fn, dump_page_body_fn)
    raise_if_browser_network_error_fn(driver, stage=f"pre_click:{tag}")

    click_error = None
    strategies = [
        lambda: el.click(),
        lambda: (
            driver.execute_script("arguments[0].scrollIntoView({block:'center', inline:'center'});", el),
            el.click(),
        ),
        lambda: driver.execute_script("arguments[0].click();", el),
        lambda: driver.execute_script(
            """
            const node = arguments[0];
            if (!node) return false;
            try { node.focus(); } catch (e) {}
            for (const type of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {
              try {
                node.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window }));
              } catch (e) {}
            }
            return true;
            """,
            el,
        ),
    ]
    for strategy in strategies:
        try:
            strategy()
            click_error = None
            break
        except Exception as exc:
            click_error = exc

    if click_error is not None:
        raise click_error

    raise_if_browser_network_error_fn(driver, stage=f"post_click:{tag}")
