from __future__ import annotations

from typing import Any, Callable

from .consent_flow import (
    maybe_click_consent_continue_once,
    maybe_recover_from_terms_page,
    wait_for_callback_navigation,
)
from .oauth_flow import validate_callback_url


def finish_register_callback(
    *,
    driver,
    oauth: Any,
    proxy: str | None,
    address_jwt: str,
    pwd: str,
    first_name: str,
    last_name: str,
    birthdate: str,
    click_final_continue_if_present: Callable[[], bool],
    find_visible: Callable[..., Any],
    dbg: Callable[..., Any],
    dump_page_body: Callable[..., Any],
    save_error_artifacts: Callable[..., Any],
    submit_callback_url: Callable[..., tuple[str, str]],
    before_wait_check_fn: Callable[[], None] | None = None,
    skip_submit: bool = False,
    callback_url_contains: str = "localhost:1455",
) -> tuple[str, str]:
    wait_for_callback_navigation(
        driver=driver,
        maybe_recover_from_terms_page_fn=lambda: maybe_recover_from_terms_page(
            driver=driver,
            dbg_fn=dbg,
            dump_page_body_fn=dump_page_body,
        ),
        maybe_click_consent_continue_once_fn=lambda: maybe_click_consent_continue_once(
            driver=driver,
            click_final_continue_if_present_fn=click_final_continue_if_present,
            dbg_fn=dbg,
            find_visible_fn=find_visible,
            callback_url_contains=callback_url_contains,
        ),
        dump_page_body_fn=dump_page_body,
        save_error_artifacts_fn=save_error_artifacts,
        before_wait_check_fn=before_wait_check_fn,
        callback_url_contains=callback_url_contains,
    )

    callback_url = driver.current_url
    if skip_submit:
        validate_callback_url(
            callback_url=callback_url,
            expected_state=oauth.state,
        )
        return "", callback_url

    reg_email, call_back = submit_callback_url(
        callback_url=callback_url,
        expected_state=oauth.state,
        code_verifier=oauth.code_verifier,
        redirect_uri=oauth.redirect_uri,
        proxy=proxy,
        mailbox_ref=address_jwt,
        password=pwd,
        first_name=first_name,
        last_name=last_name,
        birthdate=birthdate,
    )
    return reg_email, call_back
