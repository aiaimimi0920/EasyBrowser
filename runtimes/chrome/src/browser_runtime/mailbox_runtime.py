from __future__ import annotations

import json
from typing import Any, Callable, Optional


def load_json_config(path: str) -> dict:
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            return json.load(handle)
    except FileNotFoundError:
        return {}


def domain_of_email(email: str) -> str:
    value = str(email or '').strip().lower()
    if '@' not in value:
        return ''
    return value.split('@', 1)[1].strip()


def domain_health_score(domain: str, *, mail_domain_health_order: list[str]) -> int:
    value = str(domain or '').strip().lower()
    if not value:
        return -10_000
    try:
        idx = mail_domain_health_order.index(value)
        return 10_000 - idx
    except ValueError:
        return 0


def pick_mailcreate_with_health(
    *,
    mailcreate_domain: str,
    mail_domain_health_order: list[str],
    mailbox_pick_tries: int,
    create_mailbox_fn: Callable[..., Any],
    mailcreate_base_url: str,
    mailcreate_custom_auth: str,
    gptmail_base_url: str,
    gptmail_api_key: str,
    gptmail_keys_file: str,
    gptmail_prefix: Optional[str],
    gptmail_domain: Optional[str],
    mailtm_api_base: str,
):
    _ = mail_domain_health_order
    _ = mailbox_pick_tries
    return create_mailbox_fn(
        provider='self-hosted',
        mailcreate_base_url=mailcreate_base_url,
        mailcreate_custom_auth=mailcreate_custom_auth,
        mailcreate_domain=str(mailcreate_domain or '').strip(),
        gptmail_base_url=gptmail_base_url,
        gptmail_api_key=gptmail_api_key,
        gptmail_keys_file=gptmail_keys_file,
        gptmail_prefix=gptmail_prefix,
        gptmail_domain=gptmail_domain,
        mailtm_api_base=mailtm_api_base,
    )


def create_temp_mailbox(
    *,
    mailbox_provider: str,
    pick_mailcreate_with_health_fn: Callable[[], Any],
    create_mailbox_fn: Callable[..., Any],
    mailcreate_base_url: str,
    mailcreate_custom_auth: str,
    mailcreate_domain: str,
    gptmail_base_url: str,
    gptmail_api_key: str,
    gptmail_keys_file: str,
    gptmail_prefix: Optional[str],
    gptmail_domain: Optional[str],
    mailtm_api_base: str,
) -> tuple[str, str]:
    _ = pick_mailcreate_with_health_fn
    mailbox = create_mailbox_fn(
        provider=mailbox_provider,
        mailcreate_base_url=mailcreate_base_url,
        mailcreate_custom_auth=mailcreate_custom_auth,
        mailcreate_domain=mailcreate_domain,
        gptmail_base_url=gptmail_base_url,
        gptmail_api_key=gptmail_api_key,
        gptmail_keys_file=gptmail_keys_file,
        gptmail_prefix=gptmail_prefix,
        gptmail_domain=gptmail_domain,
        mailtm_api_base=mailtm_api_base,
        prefer_raw_self_hosted_ref=True,
    )
    return mailbox.email, mailbox.ref


def wait_openai_code(
    *,
    address_jwt: str,
    timeout_seconds: int,
    mailbox_provider: str,
    mailcreate_base_url: str,
    mailcreate_custom_auth: str,
    gptmail_base_url: str,
    gptmail_api_key: str,
    gptmail_keys_file: str,
    mailtm_api_base: str,
    wait_openai_code_by_provider_fn: Callable[..., str],
) -> str:
    ref = str(address_jwt or '').strip()
    ref_prefix = ref.split(':', 1)[0] if ':' in ref else 'unknown'
    print(
        f"[mailbox] wait_openai_code start provider={mailbox_provider} ref_prefix={ref_prefix} "
        f"mailcreate_auth_set={bool(mailcreate_custom_auth)} gptmail_api_key_set={bool(gptmail_api_key)}"
    )
    try:
        code = wait_openai_code_by_provider_fn(
            provider=mailbox_provider,
            mailbox_ref=address_jwt,
            mailcreate_base_url=mailcreate_base_url,
            mailcreate_custom_auth=mailcreate_custom_auth,
            gptmail_base_url=gptmail_base_url,
            gptmail_api_key=gptmail_api_key,
            gptmail_keys_file=gptmail_keys_file,
            mailtm_api_base=mailtm_api_base,
            timeout_seconds=timeout_seconds,
        )
    except Exception as exc:
        print(
            f"[mailbox] wait_openai_code fail ref_prefix={ref_prefix} "
            f"err_type={type(exc).__name__} err={exc}"
        )
        raise

    print(f"[mailbox] wait_openai_code ok ref_prefix={ref_prefix} code_len={len(str(code or ''))}")
    return code
