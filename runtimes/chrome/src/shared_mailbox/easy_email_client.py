from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from .cloudflare_temp_email_client import (
    get_direct_mailbox_latest_id,
    is_direct_mailbox_ref,
    wait_direct_mailbox_code,
)


DEFAULT_OTP_POLL_INTERVAL_SECONDS = 4


@dataclass(frozen=True)
class Mailbox:
    provider: str
    email: str
    ref: str
    session_id: str


def _mail_service_base_url() -> str:
    value = (os.environ.get("MAILBOX_SERVICE_BASE_URL") or "").strip().rstrip("/")
    if not value:
        raise RuntimeError("MAILBOX_SERVICE_BASE_URL is required")
    return value


def _mail_service_headers() -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    api_key = (os.environ.get("MAILBOX_SERVICE_API_KEY") or "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _post_json(path: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        _mail_service_base_url() + path,
        data=data,
        headers=_mail_service_headers(),
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"mail service POST {path} failed: HTTP {exc.code}: {body[:200]}") from exc


def _get_json(path: str) -> dict:
    req = urllib.request.Request(
        _mail_service_base_url() + path,
        headers=_mail_service_headers(),
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"mail service GET {path} failed: HTTP {exc.code}: {body[:200]}") from exc


def _probe_mail_service() -> str:
    try:
        req = urllib.request.Request(
            _mail_service_base_url() + "/mail/snapshot",
            headers=_mail_service_headers(),
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            return f"ok:{response.status}"
    except urllib.error.HTTPError as exc:
        return f"http_error:{exc.code}"
    except Exception as exc:
        return f"error:{type(exc).__name__}:{exc}"


def _parse_mail_timestamp(value: str) -> int:
    text = str(value or "").strip()
    if not text:
        return 0
    normalized = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except Exception:
        return 0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def _mail_dispatch_code_marker(code_obj: dict) -> int:
    if not isinstance(code_obj, dict):
        return 0
    return max(
        _parse_mail_timestamp(str(code_obj.get("receivedAt") or "")),
        _parse_mail_timestamp(str(code_obj.get("observedAt") or "")),
    )


def _normalize_provider(provider: str) -> str:
    p = (provider or os.environ.get("MAILBOX_PROVIDER") or "mailtm").strip().lower()
    if p in ("self", "local", "mailcreate", "self-hosted"):
        return "self-hosted"
    if p in ("gpt", "gptmail"):
        return "gptmail"
    if p in ("duck", "duckmail"):
        return "duckmail"
    if p in ("tempmail-lol", "tempmail.lol", "tempmaillol"):
        return "tempmail-lol"
    if p in ("mailtm", "mail.tm"):
        return "mailtm"
    if p in (
        "im215",
        "moemail",
        "guerrillamail",
        "mail2925",
        "tmailor",
        "cloudflare_temp_email",
    ):
        return p
    return p or (os.environ.get("MAILBOX_PROVIDER_FALLBACK", "mailtm").strip() or "mailtm")


def _resolve_mailbox_strategy_payload() -> dict:
    raw = (
        os.environ.get("MAILBOX_STRATEGY_MODE_JSON")
        or os.environ.get("REGISTER_INBOX_STRATEGY_MODE_JSON")
        or ""
    ).strip()
    if not raw:
        return {}

    try:
        parsed = json.loads(raw)
    except Exception:
        return {}

    payload: dict[str, object] = {}
    mode_id = str(parsed.get("modeId") or "").strip()
    if mode_id:
        payload["providerStrategyModeId"] = mode_id

    provider_selections = parsed.get("providerSelections")
    if isinstance(provider_selections, list):
        normalized: list[str] = []
        for item in provider_selections:
            value = str(item or "").strip().lower()
            if value in ("self", "local", "self-hosted"):
                normalized.append("self-hosted")
            elif value in ("gpt", "gptmail"):
                normalized.append("gptmail")
            elif value in ("mail-tm", "mailtm", "mail.tm"):
                normalized.append("mailtm")
            elif value in ("duck", "duckmail"):
                normalized.append("duckmail")
            elif value in ("tempmail-lol", "tempmail.lol", "tempmaillol"):
                normalized.append("tempmail-lol")
        if normalized:
            payload["providerGroupSelections"] = normalized

    return payload


def _mailbox_host_id(default_host_id: str) -> str:
    return (os.environ.get("MAILBOX_HOST_ID") or default_host_id).strip() or default_host_id


def _mailbox_source(default_host_id: str) -> str:
    host_id = _mailbox_host_id(default_host_id)
    return (os.environ.get("MAILBOX_SOURCE") or host_id).strip() or host_id


def _encode_ref(provider: str, session_id: str) -> str:
    return f"{provider}:{session_id}"


def _decode_ref(ref: str) -> tuple[str, str]:
    value = (ref or "").strip()
    if ":" not in value:
        provider = _normalize_provider(os.environ.get("MAILBOX_PROVIDER") or "mailtm")
        return provider, value
    provider, session_id = value.split(":", 1)
    return _normalize_provider(provider), session_id.strip()


def find_mailbox_by_email(
    *,
    email: str,
    preferred_provider: str = "",
    default_base_url: str = "",
    default_custom_auth: str = "",
) -> Mailbox | None:
    target_email = str(email or "").strip().lower()
    if not target_email:
        return None

    preferred_provider_key = _normalize_provider(preferred_provider) if str(preferred_provider or "").strip() else ""
    try:
        response = _get_json("/mail/snapshot")
    except Exception:
        return None

    snapshot = response.get("snapshot")
    if not isinstance(snapshot, dict):
        return None

    sessions = snapshot.get("sessions")
    if not isinstance(sessions, list):
        return None

    ranked: list[tuple[tuple[int, int, int, int, int], Mailbox]] = []
    now_ts = int(time.time())
    for item in sessions:
        if not isinstance(item, dict):
            continue
        item_email = str(item.get("emailAddress") or "").strip().lower()
        if item_email != target_email:
            continue
        session_id = str(item.get("id") or "").strip()
        if not session_id:
            continue
        provider_key = _normalize_provider(str(item.get("providerTypeKey") or preferred_provider_key or "mailtm"))
        raw_mailbox_ref = str(item.get("mailboxRef") or "").strip()
        effective_ref = _encode_ref(provider_key, session_id)
        if provider_key == "self-hosted" and raw_mailbox_ref and is_direct_mailbox_ref(
            raw_mailbox_ref,
            default_base_url=default_base_url,
            default_custom_auth=default_custom_auth,
        ):
            effective_ref = raw_mailbox_ref

        metadata = item.get("metadata")
        metadata_dict = metadata if isinstance(metadata, dict) else {}
        created_ts = _parse_mail_timestamp(str(item.get("createdAt") or ""))
        last_code_ts = _parse_mail_timestamp(str(metadata_dict.get("lastCodeObservedAt") or ""))
        expires_ts = _parse_mail_timestamp(str(item.get("expiresAt") or ""))
        status = str(item.get("status") or "").strip().lower()
        rank = (
            1 if preferred_provider_key and provider_key == preferred_provider_key else 0,
            1 if status in ("resolved", "active", "open") else 0,
            1 if last_code_ts > 0 else 0,
            last_code_ts,
            created_ts if created_ts > 0 else expires_ts if expires_ts > 0 else now_ts,
        )
        ranked.append(
            (
                rank,
                Mailbox(
                    provider=provider_key,
                    email=str(item.get("emailAddress") or "").strip(),
                    ref=effective_ref,
                    session_id=session_id,
                ),
            )
        )

    if not ranked:
        return None

    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return ranked[0][1]


def create_mailbox(
    *,
    provider: str = "",
    mailcreate_base_url: str = "",
    mailcreate_custom_auth: str = "",
    mailcreate_domain: str = "",
    requested_email_address: Optional[str] = None,
    requested_local_part: Optional[str] = None,
    gptmail_base_url: str = "",
    gptmail_api_key: str = "",
    gptmail_keys_file: str = "",
    gptmail_prefix: Optional[str] = None,
    gptmail_domain: Optional[str] = None,
    mailtm_api_base: str = "",
    default_host_id: str = "python-browser-service",
    prefer_raw_self_hosted_ref: bool = False,
) -> Mailbox:
    normalized_requested_email = str(requested_email_address or "").strip().lower()
    if normalized_requested_email and "@" in normalized_requested_email:
        requested_local_part = normalized_requested_email.split("@", 1)[0].strip()
        mailcreate_domain = normalized_requested_email.split("@", 1)[1].strip().lower()
    _ = mailcreate_base_url
    _ = mailcreate_custom_auth
    _ = gptmail_base_url
    _ = gptmail_api_key
    _ = gptmail_keys_file
    _ = gptmail_prefix
    _ = gptmail_domain
    _ = mailtm_api_base

    requested_provider = str(provider or os.environ.get("MAILBOX_PROVIDER") or "auto").strip().lower()
    provider_key: str | None = None
    if requested_provider not in ("", "auto", "any", "strategy"):
        provider_key = _normalize_provider(requested_provider)

    provision_mode = "always-create-dedicated"
    binding_mode = "dedicated-instance"
    preferred_instance_id = (os.environ.get("MAILBOX_PROVIDER_INSTANCE_ID") or "").strip()
    if provider_key == "self-hosted":
        provision_mode = "auto-create-if-missing"
        binding_mode = "shared-instance"
    elif provider_key is None:
        provision_mode = "auto-create-if-missing"
        binding_mode = "shared-instance"
    payload = {
        "hostId": _mailbox_host_id(default_host_id),
        "provisionMode": provision_mode,
        "bindingMode": binding_mode,
        "ttlMinutes": int((os.environ.get("MAILBOX_TTL_MINUTES") or "15").strip() or "15"),
        "metadata": {
            "source": _mailbox_source(default_host_id),
        },
    }
    if provider_key:
        payload["providerTypeKey"] = provider_key
    else:
        payload.update(_resolve_mailbox_strategy_payload())
    if normalized_requested_email:
        payload["metadata"]["requestedEmailAddress"] = normalized_requested_email
    if requested_local_part:
        payload["metadata"]["requestedLocalPart"] = str(requested_local_part).strip()
    requested_domain = str(mailcreate_domain or "").strip().lower()
    if requested_domain:
        payload["metadata"]["requestedDomain"] = requested_domain
        payload["metadata"]["mailcreateDomain"] = requested_domain
    if preferred_instance_id:
        payload["preferredInstanceId"] = preferred_instance_id
    response = _post_json("/mail/mailboxes/open", payload)
    result = response.get("result") or {}
    session = result.get("session") or {}
    session_id = str(session.get("id") or "").strip()
    email = str(session.get("emailAddress") or "").strip()
    mailbox_ref = str(session.get("mailboxRef") or "").strip()
    resolved_provider = str(session.get("providerTypeKey") or provider_key or _normalize_provider("")).strip()
    if not session_id or not email:
        raise RuntimeError("mail service returned invalid mailbox session")
    if normalized_requested_email and email.strip().lower() != normalized_requested_email:
        raise RuntimeError(
            "mail service returned mismatched mailbox email: "
            f"requested={normalized_requested_email} actual={email or '<missing>'}"
        )
    ref = _encode_ref(resolved_provider, session_id)
    if resolved_provider == "self-hosted" and prefer_raw_self_hosted_ref and mailbox_ref:
        ref = mailbox_ref
    return Mailbox(provider=resolved_provider, email=email, ref=ref, session_id=session_id)


def wait_openai_code(
    *,
    provider: str = "",
    mailbox_ref: str | None = None,
    session_id: str | None = None,
    address_jwt: str | None = None,
    mailcreate_base_url: str = "",
    mailcreate_custom_auth: str = "",
    gptmail_base_url: str = "",
    gptmail_api_key: str = "",
    gptmail_keys_file: str = "",
    mailtm_api_base: str = "",
    timeout_seconds: int = 180,
    min_mail_id: int = 0,
) -> str:
    _ = provider
    _ = mailcreate_base_url
    _ = mailcreate_custom_auth
    _ = gptmail_base_url
    _ = gptmail_api_key
    _ = gptmail_keys_file
    _ = mailtm_api_base

    ref = (mailbox_ref or address_jwt or "").strip()
    if not ref:
        raise RuntimeError("mailbox_ref is required")
    if is_direct_mailbox_ref(
        ref,
        default_base_url=mailcreate_base_url,
        default_custom_auth=mailcreate_custom_auth,
    ):
        print(f"[mailbox] wait_openai_code direct_ref timeout_seconds={timeout_seconds}")
        return wait_direct_mailbox_code(
            mailbox_ref=ref,
            default_base_url=mailcreate_base_url,
            default_custom_auth=mailcreate_custom_auth,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=max(
                1,
                int(
                    (os.environ.get("MAILBOX_POLL_INTERVAL_SECONDS") or str(DEFAULT_OTP_POLL_INTERVAL_SECONDS)).strip()
                    or str(DEFAULT_OTP_POLL_INTERVAL_SECONDS)
                ),
            ),
            min_mail_id=max(0, int(min_mail_id or 0)),
        )
    effective_session_id = str(session_id or "").strip()
    if not effective_session_id:
        _, effective_session_id = _decode_ref(ref)
    if not effective_session_id:
        raise RuntimeError("mailbox_ref is invalid")

    try:
        base_url = _mail_service_base_url()
    except Exception:
        base_url = ""
    print(
        "[mailbox] wait_openai_code mail-dispatch "
        f"base={base_url or '<missing>'} "
        f"session_id={effective_session_id} "
        f"probe={_probe_mail_service() if base_url else 'base_url_missing'} "
        f"timeout_seconds={timeout_seconds}"
    )

    deadline = time.time() + max(5, int(timeout_seconds))
    poll_interval = max(
        1,
        int(
            (os.environ.get("MAILBOX_POLL_INTERVAL_SECONDS") or str(DEFAULT_OTP_POLL_INTERVAL_SECONDS)).strip()
            or str(DEFAULT_OTP_POLL_INTERVAL_SECONDS)
        ),
    )
    while time.time() < deadline:
        response = _get_json(f"/mail/mailboxes/{effective_session_id}/code")
        code_obj = response.get("code")
        if isinstance(code_obj, dict):
            code = str(code_obj.get("code") or "").strip()
            code_marker = _mail_dispatch_code_marker(code_obj)
            if code and (int(min_mail_id or 0) <= 0 or code_marker > int(min_mail_id or 0)):
                print(
                    "[mailbox] wait_openai_code received "
                    f"session_id={effective_session_id} code_len={len(code)} code_marker={code_marker}"
                )
                return code
        time.sleep(poll_interval)
    raise RuntimeError("timeout waiting for 6-digit code")


def get_mailbox_latest_message_id(
    *,
    mailbox_ref: str | None = None,
    session_id: str | None = None,
    address_jwt: str | None = None,
    mailcreate_base_url: str = "",
    mailcreate_custom_auth: str = "",
) -> int:
    effective_session_id = str(session_id or "").strip()
    ref = (mailbox_ref or address_jwt or "").strip()
    if not ref and not effective_session_id:
        return 0
    if ref and is_direct_mailbox_ref(
        ref,
        default_base_url=mailcreate_base_url,
        default_custom_auth=mailcreate_custom_auth,
    ):
        return get_direct_mailbox_latest_id(
            mailbox_ref=ref,
            default_base_url=mailcreate_base_url,
            default_custom_auth=mailcreate_custom_auth,
        )
    if not effective_session_id and ref:
        _, effective_session_id = _decode_ref(ref)
    if not effective_session_id:
        return 0
    try:
        response = _get_json(f"/mail/mailboxes/{effective_session_id}/code")
    except Exception:
        return 0
    code_obj = response.get("code")
    if not isinstance(code_obj, dict):
        return 0
    return _mail_dispatch_code_marker(code_obj)

