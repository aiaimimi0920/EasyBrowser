from __future__ import annotations

from typing import Any, Callable

from .register_auth_flow import run_register_auth_flow
from .register_callback_flow import finish_register_callback
from .register_profile_flow import prepare_register_profile


def _is_phone_wall_error(exc: Exception) -> bool:
    message = str(exc or "").lower()
    return "phone number required" in message or "add-phone" in message


def _is_terms_block_error(exc: Exception) -> bool:
    message = str(exc or "").lower()
    return (
        "terms of use restriction on about-you page" in message
        or "can't create your account due to our terms of use" in message
        or "cannot create your account due to our terms of use" in message
    )


def _is_chatgpt_web_logged_in(driver) -> bool:
    try:
        current_url = str(getattr(driver, "current_url", "") or "").strip().lower()
    except Exception:
        current_url = ""

    if not current_url.startswith("https://chatgpt.com/"):
        return False
    if "/auth/" in current_url or "error=" in current_url:
        return False
    return True


def _set_driver_attr(driver, name: str, value: Any) -> None:
    try:
        setattr(driver, name, value)
    except Exception:
        pass


def _get_driver_attr(driver, name: str) -> dict[str, Any] | None:
    try:
        value = getattr(driver, name, None)
        return value if isinstance(value, dict) else None
    except Exception:
        return None


def _finalize_stage_runner(*, browser_backend: str | None, native_callback_state: dict[str, Any] | None) -> str:
    backend = str(browser_backend or "").strip().lower()
    if backend == "camoufox":
        return "native-camoufox" if isinstance(native_callback_state, dict) and native_callback_state.get("callbackMatched") else "selenium-fallback"
    return "selenium"


def run_register_flow(
    *,
    driver,
    proxy: str | None = None,
    captcha_provider: str | None = None,
    browser_backend: str | None = None,
    get_email_fn: Callable[..., tuple[str, str]],
    generate_oauth_url_fn: Callable[[], Any],
    dbg_fn: Callable[..., Any],
    dump_page_body_fn: Callable[..., Any],
    raise_if_browser_network_error_fn: Callable[..., Any],
    smart_wait_fn: Callable[..., Any],
    click_with_debug_fn: Callable[..., Any],
    human_mouse_jitter_fn: Callable[..., Any],
    human_type_fn: Callable[..., Any],
    human_delay_fn: Callable[..., Any],
    generate_pwd_fn: Callable[..., str],
    get_oai_code_fn: Callable[..., str],
    otp_timeout_seconds: int,
    generate_name_fn: Callable[[], tuple[str, str]],
    enter_birthday_fn: Callable[[Any], str],
    fill_about_you_birthday_segments_fn: Callable[..., dict | None],
    force_submit_about_you_form_fn: Callable[..., dict | None],
    click_final_continue_if_present_fn: Callable[[], bool],
    find_visible_fn: Callable[..., Any],
    save_error_artifacts_fn: Callable[..., Any],
    submit_callback_url_fn: Callable[..., tuple[str, str]],
    repairer_drive_login_and_get_callback_url_fn: Callable[..., tuple[str, str]] | None = None,
) -> tuple[str, str]:
    dbg_fn("register", "start stage 1: create account via chatgpt web channel", driver=driver)

    from .oauth_flow import generate_chatgpt_web_oauth_url
    
    # 【两步走改造：Step 1】使用 ChatGPT Web channel 避免 phone_wall
    auth_state = run_register_auth_flow(
        driver=driver,
        proxy=proxy,
        get_email=get_email_fn,
        generate_oauth_url=generate_chatgpt_web_oauth_url,
        _dbg=dbg_fn,
        _dump_page_body=dump_page_body_fn,
        _raise_if_browser_network_error=raise_if_browser_network_error_fn,
        smart_wait=smart_wait_fn,
        _click_with_debug=click_with_debug_fn,
        _human_mouse_jitter=human_mouse_jitter_fn,
        _human_type=human_type_fn,
        _human_delay=human_delay_fn,
        generate_pwd=generate_pwd_fn,
        get_oai_code=get_oai_code_fn,
        OTP_TIMEOUT_SECONDS=otp_timeout_seconds,
        captcha_provider=captcha_provider,
        browser_backend=browser_backend,
    )

    email = str(auth_state.get("email") or "")
    address_jwt = str(auth_state.get("address_jwt") or "")
    oauth = auth_state.get("oauth")
    pwd = str(auth_state.get("pwd") or "")

    profile_state = prepare_register_profile(
        driver=driver,
        generate_name=generate_name_fn,
        enter_birthday=enter_birthday_fn,
        click_with_debug=click_with_debug_fn,
        dbg=dbg_fn,
        dump_page_body=dump_page_body_fn,
        fill_about_you_birthday_segments=fill_about_you_birthday_segments_fn,
        force_submit_about_you_form=force_submit_about_you_form_fn,
    )

    first_name = str(profile_state.get("first_name") or "")
    last_name = str(profile_state.get("last_name") or "")
    birthdate = str(profile_state.get("birthdate") or "")
    _set_driver_attr(driver, "_neuro_register_finalize_stage1", None)
    _set_driver_attr(driver, "_neuro_register_finalize_stage2", None)
    _set_driver_attr(driver, "_neuro_finalize_callback_state", None)
    _set_driver_attr(driver, "_neuro_repair_flow_result", None)

    def _raise_if_add_phone_page() -> None:
        try:
            current_url = str(getattr(driver, "current_url", "") or "").lower()
            body_text_raw = str(
                driver.execute_script(
                    "return (document && document.body && document.body.innerText) ? document.body.innerText : '';"
                )
                or ""
            )
            body_text = body_text_raw.lower()
            title_text = str(
                driver.execute_script("return (document && document.title) ? document.title : '';") or ""
            ).lower()
        except Exception:
            return

        if (
            "/add-phone" in current_url
            or "phone number required" in body_text
            or "phone number required" in title_text
            or "需要手机号" in body_text_raw
            or ("手机" in body_text_raw and "号码" in body_text_raw and "需要" in body_text_raw)
        ):
            raise RuntimeError("Blocked: Phone number required on OpenAI add-phone page.")
        if (
            "auth.openai.com/about-you" in current_url
            and (
                "we can't create your account due to our terms of use" in body_text
                or "we cannot create your account due to our terms of use" in body_text
                or ("terms of use" in body_text and "can't create your account" in body_text)
                or ("terms of use" in body_text and "cannot create your account" in body_text)
            )
        ):
            raise RuntimeError("Blocked: Terms of Use restriction on about-you page.")

    try:
        _, stage1_callback_url = finish_register_callback(
            driver=driver,
            oauth=oauth,
            proxy=proxy,
            address_jwt=address_jwt,
            pwd=pwd,
            first_name=first_name,
            last_name=last_name,
            birthdate=birthdate,
            click_final_continue_if_present=click_final_continue_if_present_fn,
            find_visible=find_visible_fn,
            dbg=dbg_fn,
            dump_page_body=dump_page_body_fn,
            save_error_artifacts=save_error_artifacts_fn,
            submit_callback_url=submit_callback_url_fn,
            before_wait_check_fn=_raise_if_add_phone_page,
            skip_submit=True,
            callback_url_contains="chatgpt.com/api/auth/callback/openai",
        )
        stage1_native_callback_state = _get_driver_attr(driver, "_neuro_finalize_callback_state")
        _set_driver_attr(driver, "_neuro_register_finalize_stage1", {
            "callback_url": str(stage1_callback_url or ""),
            "mode": "chatgpt-callback",
            "runner": _finalize_stage_runner(
                browser_backend=browser_backend,
                native_callback_state=stage1_native_callback_state,
            ),
            "native_callback_state": stage1_native_callback_state,
        })
        
        # =========================================================================
        # 【两步走改造：Step 2】
        # ChatGPT Web channel 建号成功。账号存在了！
        # 现在利用现成的 repairer login 流，以 Codex Client 的身份登录换 Token。
        # 用新账号 Login 极大概率不会触发 phone wall！
        # =========================================================================
        dbg_fn("register", "stage 1 finished. starting stage 2: login via codex channel", driver=driver)
        if repairer_drive_login_and_get_callback_url_fn is None:
            raise RuntimeError("repairer_drive_login_and_get_callback_url_fn is required for two-step registration")

        codex_oauth = generate_oauth_url_fn()
        _set_driver_attr(driver, "_neuro_finalize_callback_state", None)
        _set_driver_attr(driver, "_neuro_repair_flow_result", None)
        stage2_callback_url, chosen_mailbox_ref = repairer_drive_login_and_get_callback_url_fn(
            driver=driver,
            oauth=codex_oauth,
            email=email,
            password=pwd,
            mailbox_ref_candidates=[address_jwt],
        )
        stage2_native_callback_state = _get_driver_attr(driver, "_neuro_finalize_callback_state")
        stage2_repair_flow = _get_driver_attr(driver, "_neuro_repair_flow_result")
        _set_driver_attr(driver, "_neuro_register_finalize_stage2", {
            "callback_url": str(stage2_callback_url or ""),
            "mailbox_ref": str(chosen_mailbox_ref or address_jwt or ""),
            "mode": str((stage2_repair_flow or {}).get("mode") or ""),
            "runner": str((stage2_repair_flow or {}).get("runner") or _finalize_stage_runner(
                browser_backend=browser_backend,
                native_callback_state=stage2_native_callback_state,
            )),
            "native_callback_state": stage2_native_callback_state,
        })

        reg_email, config_json, submit_meta = submit_callback_url_fn(
            callback_url=stage2_callback_url,
            expected_state=codex_oauth.state,
            code_verifier=codex_oauth.code_verifier,
            redirect_uri=codex_oauth.redirect_uri,
            proxy=proxy,
            mailbox_ref=(chosen_mailbox_ref or address_jwt),
            password=pwd,
            first_name=first_name,
            last_name=last_name,
            birthdate=birthdate,
            return_metadata=True,
        )
        _set_driver_attr(driver, "_neuro_register_finalize_stage2", {
            **(_get_driver_attr(driver, "_neuro_register_finalize_stage2") or {}),
            "validate_status": str((submit_meta or {}).get("validateStatus") or ""),
            "token_exchange_status": str((submit_meta or {}).get("tokenExchangeStatus") or ""),
            "token_response_status": str((submit_meta or {}).get("tokenResponseStatus") or ""),
            "claims_status": str((submit_meta or {}).get("claimsStatus") or ""),
            "auth_payload_status": str((submit_meta or {}).get("authPayloadStatus") or ""),
            "email": str((submit_meta or {}).get("email") or reg_email or ""),
        })
        return reg_email, config_json

    except RuntimeError as exc:
        if _is_terms_block_error(exc):
            raise
        phone_wall = _is_phone_wall_error(exc)
        chatgpt_web_logged_in = _is_chatgpt_web_logged_in(driver)

        if repairer_drive_login_and_get_callback_url_fn is None:
            raise
        if not phone_wall and not chatgpt_web_logged_in:
            raise

        if phone_wall:
            dbg_fn("repair", "phone wall detected in stage 1, switching to login recovery flow directly", driver=driver)
        else:
            dbg_fn(
                "repair",
                "stage 1 reached logged-in chatgpt web without callback, switching to codex login flow",
                driver=driver,
            )

        codex_oauth = generate_oauth_url_fn()
        _set_driver_attr(driver, "_neuro_finalize_callback_state", None)
        _set_driver_attr(driver, "_neuro_repair_flow_result", None)
        callback_url, chosen_mailbox_ref = repairer_drive_login_and_get_callback_url_fn(
            driver=driver,
            oauth=codex_oauth,
            email=email,
            password=pwd,
            mailbox_ref_candidates=[address_jwt],
        )
        stage2_native_callback_state = _get_driver_attr(driver, "_neuro_finalize_callback_state")
        stage2_repair_flow = _get_driver_attr(driver, "_neuro_repair_flow_result")
        _set_driver_attr(driver, "_neuro_register_finalize_stage2", {
            "callback_url": str(callback_url or ""),
            "mailbox_ref": str(chosen_mailbox_ref or address_jwt or ""),
            "mode": str((stage2_repair_flow or {}).get("mode") or ""),
            "runner": str((stage2_repair_flow or {}).get("runner") or _finalize_stage_runner(
                browser_backend=browser_backend,
                native_callback_state=stage2_native_callback_state,
            )),
            "native_callback_state": stage2_native_callback_state,
        })
        reg_email, config_json, submit_meta = submit_callback_url_fn(
            callback_url=callback_url,
            expected_state=codex_oauth.state,
            code_verifier=codex_oauth.code_verifier,
            redirect_uri=codex_oauth.redirect_uri,
            proxy=proxy,
            mailbox_ref=(chosen_mailbox_ref or address_jwt),
            password=pwd,
            first_name=first_name,
            last_name=last_name,
            birthdate=birthdate,
            return_metadata=True,
        )
        _set_driver_attr(driver, "_neuro_register_finalize_stage2", {
            **(_get_driver_attr(driver, "_neuro_register_finalize_stage2") or {}),
            "validate_status": str((submit_meta or {}).get("validateStatus") or ""),
            "token_exchange_status": str((submit_meta or {}).get("tokenExchangeStatus") or ""),
            "token_response_status": str((submit_meta or {}).get("tokenResponseStatus") or ""),
            "claims_status": str((submit_meta or {}).get("claimsStatus") or ""),
            "auth_payload_status": str((submit_meta or {}).get("authPayloadStatus") or ""),
            "email": str((submit_meta or {}).get("email") or reg_email or ""),
        })
        return reg_email, config_json
