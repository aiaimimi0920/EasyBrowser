from __future__ import annotations

import json
import os
import re
import shutil
import socket
import threading
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any

from .about_you_flow import fill_about_you_birthday_segments, force_submit_about_you_form
from .browser_debug import (
    click_with_debug as runtime_click_with_debug,
    detect_browser_network_error,
    raise_if_browser_network_error as runtime_raise_if_browser_network_error,
)
from .consent_flow import click_final_continue_if_present
from .driver_factory import (
    apply_runtime_stealth,
    build_stealth_profile,
    create_proxy_extension,
    detect_runtime_user_agent,
    new_driver as browser_new_driver,
    resolve_chrome_version_main,
)
from .humanize import human_delay, human_mouse_jitter, human_type
from .mailbox_runtime import (
    create_temp_mailbox,
    load_json_config,
    pick_mailcreate_with_health,
    wait_openai_code,
)
from .migrated_stealth_scripts import load_migrated_page_scripts
from .oauth_flow import generate_oauth_url, submit_callback_url
from .probe_core import ProbeResult
from .repairer_flow import repairer_drive_login_and_get_callback_url
from .repairer_one_file import repair_one_auth_file
from .repairer_storage import (
    append_jsonl as repairer_append_jsonl,
    deep_merge_keep_old_when_missing,
    read_json_any as repairer_read_json_any,
    write_json_any as repairer_write_json_any,
)
from .register_inputs import enter_birthday, generate_name, generate_pwd
from .register_orchestrator import run_register_flow
from .runtime_io import run_register_once as runtime_run_register_once
from shared_mailbox.easy_email_client import (
    create_mailbox,
    get_mailbox_latest_message_id as get_mailbox_latest_message_id_by_provider,
    wait_openai_code as wait_openai_code_by_provider,
)
from .stealth_helpers import env_flag, extract_user_agent_bits
from .stealth_source import build_stealth_source
from .wait_utils import find_visible, smart_wait


@dataclass(frozen=True)
class BrowserRegistrationResult:
    email: str
    auth: dict[str, Any]


driver_init_lock = threading.Lock()
repair_write_lock = threading.Lock()

_DEFAULT_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "data"))
_LEGACY_DATA_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "platformtools", "auto_register", "codex_register", "data")
)


def _seed_default_data_dir() -> None:
    os.makedirs(_DEFAULT_DATA_DIR, exist_ok=True)
    if not os.path.isdir(_LEGACY_DATA_DIR):
        return
    for filename in ("mailcreate_config.json", "gptmail_keys.txt", "proxies.txt"):
        src = os.path.join(_LEGACY_DATA_DIR, filename)
        dst = os.path.join(_DEFAULT_DATA_DIR, filename)
        if os.path.isfile(src) and not os.path.exists(dst):
            shutil.copy2(src, dst)


_seed_default_data_dir()
DATA_DIR = (os.environ.get("DATA_DIR") or _DEFAULT_DATA_DIR).strip() or _DEFAULT_DATA_DIR


def _sanitize_instance_id(v: str) -> str:
    s = (v or "").strip()
    if not s:
        return "default"
    s = re.sub(r"[^a-zA-Z0-9_.-]+", "_", s)
    return s[:64] or "default"


INSTANCE_ID = _sanitize_instance_id(
    os.environ.get("INSTANCE_ID")
    or os.environ.get("RESULTS_INSTANCE_ID")
    or os.environ.get("HOSTNAME")
    or socket.gethostname()
)

OTP_TIMEOUT_SECONDS = int(os.environ.get("OTP_TIMEOUT_SECONDS", "300") or "300")
if OTP_TIMEOUT_SECONDS <= 0:
    OTP_TIMEOUT_SECONDS = 300

MAILBOX_PROVIDER = os.environ.get("MAILBOX_PROVIDER", "auto").strip().lower()
MAILCREATE_CONFIG_FILE = os.environ.get(
    "MAILCREATE_CONFIG_FILE",
    os.path.join(DATA_DIR, "mailcreate_config.json"),
).strip()
_MAILCREATE_CFG = load_json_config(MAILCREATE_CONFIG_FILE)

MAILCREATE_BASE_URL = (
    os.environ.get("MAILCREATE_BASE_URL")
    or str(_MAILCREATE_CFG.get("MAILCREATE_BASE_URL") or "https://mail.aiaimimi.com")
).strip()
MAILCREATE_CUSTOM_AUTH = (
    os.environ.get("MAILCREATE_CUSTOM_AUTH")
    or str(_MAILCREATE_CFG.get("MAILCREATE_CUSTOM_AUTH") or "")
).strip()
MAILCREATE_DOMAIN = (
    os.environ.get("MAILCREATE_DOMAIN")
    or str(_MAILCREATE_CFG.get("MAILCREATE_DOMAIN") or "")
).strip()

GPTMAIL_BASE_URL = (os.environ.get("GPTMAIL_BASE_URL") or "https://mail.chatgpt.org.uk").strip()
GPTMAIL_API_KEY = (os.environ.get("GPTMAIL_API_KEY") or "").strip()
GPTMAIL_KEYS_FILE = os.environ.get(
    "GPTMAIL_KEYS_FILE",
    os.path.join(DATA_DIR, "gptmail_keys.txt"),
).strip()
GPTMAIL_PREFIX = os.environ.get("GPTMAIL_PREFIX", "").strip() or None
GPTMAIL_DOMAIN = os.environ.get("GPTMAIL_DOMAIN", "").strip() or None

MAILTM_API_BASE = (os.environ.get("MAILTM_API_BASE") or "https://api.mail.tm").strip()
_MAIL_DOMAIN_HEALTH_ORDER = [
    d.strip().lower()
    for d in (os.environ.get("MAIL_DOMAIN_HEALTH_ORDER") or "").split(",")
    if d.strip()
]
_MAILBOX_PICK_TRIES = int(os.environ.get("MAILBOX_PICK_TRIES", "3") or "3")
if _MAILBOX_PICK_TRIES <= 0:
    _MAILBOX_PICK_TRIES = 1


def _data_path(*parts: str) -> str:
    return os.path.join(DATA_DIR, *parts)


def _dbg(step: str, msg: str = "", *, driver=None) -> None:
    current_url = ""
    try:
        current_url = str(getattr(driver, "current_url", "") or "")
    except Exception:
        current_url = ""
    suffix = f" url={current_url}" if current_url else ""
    print(f"[python-browser-service][{step}] {msg}{suffix}", flush=True)


def _dump_page_body(*, driver, kind: str, message: str = "") -> None:
    current_url = ""
    title = ""
    body_excerpt = ""
    try:
        current_url = str(getattr(driver, "current_url", "") or "")
    except Exception:
        current_url = ""
    try:
        title = str(driver.execute_script("return (document && document.title) ? document.title : '';") or "")
    except Exception:
        title = ""
    try:
        body_text = str(
            driver.execute_script(
                "return (document && document.body && document.body.innerText) ? document.body.innerText : '';"
            )
            or ""
        )
        body_excerpt = re.sub(r"\s+", " ", body_text).strip()[:800]
    except Exception:
        body_excerpt = ""

    print(
        "[python-browser-service][page-dump] "
        f"kind={kind} message={message!r} url={current_url!r} title={title!r} body={body_excerpt!r}"
        ,
        flush=True,
    )


def _save_error_artifacts(*, driver, kind: str, message: str = "") -> None:
    current_url = ""
    try:
        current_url = str(getattr(driver, "current_url", "") or "")
    except Exception:
        current_url = ""
    print(
        "[python-browser-service][error-artifact] "
        f"kind={kind} message={message!r} url={current_url!r}"
        ,
        flush=True,
    )


def _raise_if_browser_network_error(driver, *, stage: str = "") -> None:
    runtime_raise_if_browser_network_error(
        driver,
        stage=stage,
        detect_browser_network_error_fn=detect_browser_network_error,
    )


def _click_with_debug(driver, el, *, tag: str, note: str = "") -> None:
    runtime_click_with_debug(
        driver=driver,
        el=el,
        tag=tag,
        note=note,
        dbg_fn=_dbg,
        dump_page_body_fn=_dump_page_body,
        raise_if_browser_network_error_fn=_raise_if_browser_network_error,
    )


def _smart_wait(driver, by, value, timeout=20, *, debug_kind: str = "", debug_message: str = ""):
    return smart_wait(
        driver,
        by,
        value,
        timeout,
        debug_kind=debug_kind,
        debug_message=debug_message,
        dbg_fn=_dbg,
        click_with_debug_fn=_click_with_debug,
        dump_page_body_fn=_dump_page_body,
        save_error_artifacts_fn=_save_error_artifacts,
        raise_if_browser_network_error_fn=_raise_if_browser_network_error,
    )


def _build_startup_user_agent() -> str:
    manual = (os.environ.get("STEALTH_USER_AGENT") or "").strip()
    if manual:
        return manual.replace("HeadlessChrome/", "Chrome/")

    major_version = resolve_chrome_version_main() or 145
    if os.name == "nt":
        user_agent = (
            f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            f"(KHTML, like Gecko) Chrome/{major_version}.0.0.0 Safari/537.36"
        )
    else:
        user_agent = (
            f"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            f"(KHTML, like Gecko) Chrome/{major_version}.0.0.0 Safari/537.36"
        )

    if env_flag("STEALTH_MASK_LINUX", "1") and "Linux" in user_agent and "Android" not in user_agent:
        user_agent = re.sub(r"\(([^)]+)\)", "(Windows NT 10.0; Win64; x64)", user_agent, count=1)

    return user_agent.replace("HeadlessChrome/", "Chrome/")


def _build_runtime_stealth_profile(driver, *, headless: int) -> dict[str, Any]:
    return build_stealth_profile(
        driver,
        headless=headless,
        detect_runtime_user_agent_fn=lambda current_driver: detect_runtime_user_agent(
            current_driver,
            resolve_chrome_version_main_fn=resolve_chrome_version_main,
            env_flag_fn=env_flag,
        ),
        extract_user_agent_bits_fn=extract_user_agent_bits,
    )


def _new_driver(
    proxy: str | None = None,
    *,
    browser_backend: str | None = None,
    startup_url_override: str | None = None,
):
    remove_args = {
        "--disable-extensions",
        "--disable-default-apps",
        "--disable-component-extensions-with-background-pages",
    }
    extra_remove_args_raw = str(os.environ.get("BROWSER_REMOVE_ARGS_EXTRA", "") or "").strip()
    if extra_remove_args_raw:
        for raw_part in extra_remove_args_raw.replace(";", ",").split(","):
            part = raw_part.strip()
            if part:
                remove_args.add(part)
    driver, proxy_dir = browser_new_driver(
        proxy,
        browser_backend=(browser_backend or "custom").strip() or "custom",
        create_proxy_extension_fn=create_proxy_extension,
        apply_runtime_stealth_fn=lambda current_driver, *, headless: apply_runtime_stealth(
            current_driver,
            headless=headless,
            build_stealth_profile_fn=lambda d, current_headless: _build_runtime_stealth_profile(
                d, headless=current_headless
            ),
            build_stealth_source_fn=build_stealth_source,
        ),
        resolve_chrome_version_main_fn=resolve_chrome_version_main,
        startup_user_agent=_build_startup_user_agent(),
        browser_user_data_dir=str(os.environ.get("BROWSER_USER_DATA_DIR", "") or "").strip(),
        browser_profile_directory=str(os.environ.get("BROWSER_PROFILE_DIRECTORY", "") or "").strip(),
        browser_debugger_address=str(os.environ.get("BROWSER_DEBUGGER_ADDRESS", "") or "").strip(),
        startup_url=str(startup_url_override or os.environ.get("BROWSER_STARTUP_URL", "") or "").strip(),
        remove_args=remove_args,
    )

    for migrated_script_name, migrated_script_source in load_migrated_page_scripts():
        try:
            driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {"source": migrated_script_source},
            )
        except Exception:
            _ = migrated_script_name

    return driver, proxy_dir


def _get_email(proxy: str | None = None) -> tuple[str, str]:
    _ = proxy
    return create_temp_mailbox(
        mailbox_provider=MAILBOX_PROVIDER,
        pick_mailcreate_with_health_fn=lambda: pick_mailcreate_with_health(
            mailcreate_domain=MAILCREATE_DOMAIN,
            mail_domain_health_order=_MAIL_DOMAIN_HEALTH_ORDER,
            mailbox_pick_tries=_MAILBOX_PICK_TRIES,
            create_mailbox_fn=create_mailbox,
            mailcreate_base_url=MAILCREATE_BASE_URL,
            mailcreate_custom_auth=MAILCREATE_CUSTOM_AUTH,
            gptmail_base_url=GPTMAIL_BASE_URL,
            gptmail_api_key=GPTMAIL_API_KEY,
            gptmail_keys_file=GPTMAIL_KEYS_FILE,
            gptmail_prefix=GPTMAIL_PREFIX,
            gptmail_domain=GPTMAIL_DOMAIN,
            mailtm_api_base=MAILTM_API_BASE,
        ),
        create_mailbox_fn=create_mailbox,
        mailcreate_base_url=MAILCREATE_BASE_URL,
        mailcreate_custom_auth=MAILCREATE_CUSTOM_AUTH,
        mailcreate_domain=MAILCREATE_DOMAIN,
        gptmail_base_url=GPTMAIL_BASE_URL,
        gptmail_api_key=GPTMAIL_API_KEY,
        gptmail_keys_file=GPTMAIL_KEYS_FILE,
        gptmail_prefix=GPTMAIL_PREFIX,
        gptmail_domain=GPTMAIL_DOMAIN,
        mailtm_api_base=MAILTM_API_BASE,
    )


def _get_oai_code(*, address_jwt: str, timeout_seconds: int = 180, proxy: str | None = None) -> str:
    _ = proxy
    return wait_openai_code(
        address_jwt=address_jwt,
        timeout_seconds=timeout_seconds,
        mailbox_provider=MAILBOX_PROVIDER,
        mailcreate_base_url=MAILCREATE_BASE_URL,
        mailcreate_custom_auth=MAILCREATE_CUSTOM_AUTH,
        gptmail_base_url=GPTMAIL_BASE_URL,
        gptmail_api_key=GPTMAIL_API_KEY,
        gptmail_keys_file=GPTMAIL_KEYS_FILE,
        mailtm_api_base=MAILTM_API_BASE,
        wait_openai_code_by_provider_fn=wait_openai_code_by_provider,
    )


def _submit_callback_url(**kwargs) -> tuple[str, str] | tuple[str, str, dict[str, Any]]:
    return submit_callback_url(
        **kwargs,
        token_post_verify_tls=(os.environ.get("TOKEN_POST_TLS_VERIFY", "0") or "0").strip().lower() not in ("0", "false", "no", "off"),
        token_post_try_direct_first=(os.environ.get("TOKEN_POST_TRY_DIRECT_FIRST", "1") or "1").strip().lower() not in ("0", "false", "no", "off"),
        token_post_max_retries=max(1, int(os.environ.get("TOKEN_POST_MAX_RETRIES", "6") or "6")),
    )


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _repairer_results_dir() -> str:
    path = _data_path("repairer_http_results")
    os.makedirs(path, exist_ok=True)
    return path


def _register(
    driver,
    proxy: str | None = None,
    *,
    preallocated_email: str | None = None,
    preallocated_session_id: str | None = None,
    preallocated_mailbox_ref: str | None = None,
    captcha_provider: str | None = None,
    browser_backend: str | None = None,
    precomputed_oauth: Any | None = None,
) -> tuple[str, str]:
    def _resolve_email(_proxy: str | None = None) -> tuple[str, str]:
        if preallocated_email and preallocated_mailbox_ref:
            return str(preallocated_email).strip(), str(preallocated_mailbox_ref).strip()
        if preallocated_email and preallocated_session_id:
            return str(preallocated_email).strip(), f"mail-dispatch:{str(preallocated_session_id).strip()}"
        return _get_email(_proxy)

    return run_register_flow(
        driver=driver,
        proxy=proxy,
        captcha_provider=captcha_provider,
        browser_backend=browser_backend,
        get_email_fn=_resolve_email,
        generate_oauth_url_fn=(lambda: precomputed_oauth) if precomputed_oauth is not None else generate_oauth_url,
        dbg_fn=_dbg,
        dump_page_body_fn=_dump_page_body,
        raise_if_browser_network_error_fn=_raise_if_browser_network_error,
        smart_wait_fn=_smart_wait,
        click_with_debug_fn=_click_with_debug,
        human_mouse_jitter_fn=human_mouse_jitter,
        human_type_fn=human_type,
        human_delay_fn=human_delay,
        generate_pwd_fn=generate_pwd,
        get_oai_code_fn=_get_oai_code,
        otp_timeout_seconds=OTP_TIMEOUT_SECONDS,
        generate_name_fn=generate_name,
        enter_birthday_fn=enter_birthday,
        fill_about_you_birthday_segments_fn=lambda *, iso_yyyy_mm_dd: fill_about_you_birthday_segments(
            driver,
            iso_yyyy_mm_dd=iso_yyyy_mm_dd,
        ),
        force_submit_about_you_form_fn=lambda *, full_name, iso_yyyy_mm_dd: force_submit_about_you_form(
            driver,
            full_name=full_name,
            iso_yyyy_mm_dd=iso_yyyy_mm_dd,
        ),
        click_final_continue_if_present_fn=lambda: click_final_continue_if_present(
            driver=driver,
            dbg_fn=_dbg,
            find_visible_fn=find_visible,
            click_with_debug_fn=_click_with_debug,
        ),
        find_visible_fn=find_visible,
        save_error_artifacts_fn=_save_error_artifacts,
        submit_callback_url_fn=_submit_callback_url,
        repairer_drive_login_and_get_callback_url_fn=lambda **kwargs: repairer_drive_login_and_get_callback_url(
            **kwargs,
            captcha_provider=captcha_provider,
            browser_backend=browser_backend,
            smart_wait=_smart_wait,
            click_with_debug=_click_with_debug,
            get_mailbox_latest_message_id_by_provider=get_mailbox_latest_message_id_by_provider,
            wait_openai_code_by_provider=wait_openai_code_by_provider,
            mailcreate_base_url=MAILCREATE_BASE_URL,
            mailcreate_custom_auth=MAILCREATE_CUSTOM_AUTH,
            gptmail_base_url=GPTMAIL_BASE_URL,
            gptmail_api_key=GPTMAIL_API_KEY,
            gptmail_keys_file=GPTMAIL_KEYS_FILE,
            mailtm_api_base=MAILTM_API_BASE,
            dump_page_body=_dump_page_body,
        ),
    )


def _is_recoverable_register_round_error(exc: RuntimeError) -> bool:
    msg_low = str(exc or "").lower()
    return (
        "fatal ui error page detected" in msg_low
        or "password submitted but otp stage not reached" in msg_low
        or "timeout waiting for callback url" in msg_low
        or "logged in chatgpt web without callback" in msg_low
        or "chatgpt_nextauth_fetch_status=403" in msg_low
        or "chatgpt_nextauth_fetch_status=429" in msg_low
        or "chatgpt_nextauth_fetch_error" in msg_low
    )


def _always_close_register_error(exc: Exception) -> bool:
    return "phone number required" in str(exc or "").lower()


def run_registration_once(
    *,
    proxy: str | None,
    preallocated_email: str | None = None,
    preallocated_session_id: str | None = None,
    preallocated_mailbox_ref: str | None = None,
    captcha_provider: str | None = None,
    browser_backend: str | None = None,
) -> BrowserRegistrationResult:
    headless_v = int(os.environ.get("HEADLESS", "0") or "0")
    default_keep = "1" if headless_v == 0 else "0"
    keep_open_on_fail = (
        int(os.environ.get("KEEP_BROWSER_OPEN_ON_FAIL", default_keep) or default_keep) == 1
        and headless_v == 0
    )
    max_round_retries = int(os.environ.get("MAX_REGISTER_ROUND_RETRIES", "2") or "2")
    retry_sleep_seconds = float(os.environ.get("REGISTER_ROUND_RETRY_SLEEP_SECONDS", "8.0") or "8.0")

    camoufox_oauth = generate_oauth_url() if str(browser_backend or "").strip().lower() == "camoufox" else None

    email, auth_json_text = runtime_run_register_once(
        proxy=proxy,
        keep_open_on_fail=keep_open_on_fail,
        driver_init_lock=driver_init_lock,
        new_driver=lambda proxy_value: _new_driver(
            proxy_value,
            browser_backend=browser_backend,
            startup_url_override=getattr(camoufox_oauth, "auth_url", None),
        ),
        register_fn=lambda driver, proxy_value: _register(
            driver,
            proxy_value,
            preallocated_email=preallocated_email,
            preallocated_session_id=preallocated_session_id,
            preallocated_mailbox_ref=preallocated_mailbox_ref,
            captcha_provider=captcha_provider,
            browser_backend=browser_backend,
            precomputed_oauth=camoufox_oauth,
        ),
        max_round_retries=max_round_retries,
        retry_sleep_seconds=retry_sleep_seconds,
        recoverable_error_predicate=_is_recoverable_register_round_error,
        always_close_error_predicate=_always_close_register_error,
    )
    auth_json = json.loads(auth_json_text)
    if not isinstance(auth_json, dict):
        raise RuntimeError("browser registration returned invalid auth JSON payload")
    return BrowserRegistrationResult(email=email, auth=auth_json)


def run_browser_repair_once(
    *,
    proxy: str | None,
    auth_obj: dict[str, Any],
    browser_backend: str | None = None,
    captcha_provider: str | None = None,
) -> BrowserRegistrationResult:
    if not isinstance(auth_obj, dict):
        raise RuntimeError("browser repair requires auth object")

    temp_input_dir = _data_path("_repair_http_inputs")
    temp_output_dirname = "_repair_http_success"
    os.makedirs(temp_input_dir, exist_ok=True)

    temp_name = f"repair-{INSTANCE_ID}-{int(datetime.now(timezone.utc).timestamp() * 1000)}.json"
    temp_input_path = os.path.join(temp_input_dir, temp_name)
    temp_output_path: str | None = None

    repairer_write_json_any(temp_input_path, auth_obj)
    camoufox_oauth = generate_oauth_url() if str(browser_backend or "").strip().lower() == "camoufox" else None

    try:
        ok, reason, temp_output_path = repair_one_auth_file(
            temp_input_path,
            proxy=proxy,
            read_json_any=repairer_read_json_any,
            platformtools_dev_vars={},
            mailcreate_cfg=_MAILCREATE_CFG,
            mailcreate_base_url=MAILCREATE_BASE_URL,
            append_jsonl=repairer_append_jsonl,
            repairer_results_dir=_repairer_results_dir,
            utc_now_iso=_utc_now_iso,
            probe_wham_one=lambda *, auth_obj, proxy=None: ProbeResult(
                status_code=None,
                note="probe_skipped",
                category="probe_skipped",
            ),
            probe_result_factory=lambda **kwargs: ProbeResult(**kwargs),
            driver_init_lock=driver_init_lock,
            new_driver=lambda proxy_value: _new_driver(
                proxy_value,
                browser_backend=browser_backend,
                startup_url_override=getattr(camoufox_oauth, "auth_url", None),
            ),
            generate_oauth_url=(lambda: camoufox_oauth) if camoufox_oauth is not None else generate_oauth_url,
            repairer_drive_login_and_get_callback_url=lambda **kwargs: repairer_drive_login_and_get_callback_url(
                **kwargs,
                captcha_provider=captcha_provider,
                browser_backend=browser_backend,
                smart_wait=_smart_wait,
                click_with_debug=_click_with_debug,
                get_mailbox_latest_message_id_by_provider=get_mailbox_latest_message_id_by_provider,
                wait_openai_code_by_provider=wait_openai_code_by_provider,
                mailcreate_base_url=MAILCREATE_BASE_URL,
                mailcreate_custom_auth=MAILCREATE_CUSTOM_AUTH,
                gptmail_base_url=GPTMAIL_BASE_URL,
                gptmail_api_key=GPTMAIL_API_KEY,
                gptmail_keys_file=GPTMAIL_KEYS_FILE,
                mailtm_api_base=MAILTM_API_BASE,
                dump_page_body=_dump_page_body,
            ),
            submit_callback_url=_submit_callback_url,
            deep_merge_keep_old_when_missing=deep_merge_keep_old_when_missing,
            instance_id=INSTANCE_ID,
            data_path=_data_path,
            fixed_success_dirname=temp_output_dirname,
            write_lock=repair_write_lock,
            write_json_any=repairer_write_json_any,
        )
        if not ok or not temp_output_path:
            raise RuntimeError(reason or "browser repair failed")

        repaired = repairer_read_json_any(temp_output_path)
        if not isinstance(repaired, dict):
            raise RuntimeError("browser repair returned invalid auth payload")

        return BrowserRegistrationResult(
            email=str(repaired.get("email") or auth_obj.get("email") or "").strip(),
            auth=repaired,
        )
    finally:
        try:
            os.remove(temp_input_path)
        except Exception:
            pass
        if temp_output_path and os.path.isfile(temp_output_path):
            try:
                os.remove(temp_output_path)
            except Exception:
                pass

