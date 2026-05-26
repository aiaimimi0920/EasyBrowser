from __future__ import annotations

import json
import quopri
import re
import time
import urllib.error
import urllib.parse
import urllib.request


_TITLE_6_RE = re.compile(r"<title[^>]*>.*?(\d{6}).*?</title>", re.IGNORECASE | re.DOTALL)
_CODE_CONTEXT_RE = re.compile(
    r"(?:verification\s*code|verify\s*code|security\s*code|one[-\s]*time\s*code|otp\s*code|验证码|校验码|代码为|代码是|code\s*(?:is|:))"
    r"[^0-9]{0,40}(\d{6})",
    re.IGNORECASE | re.DOTALL,
)
_FALLBACK_6_RE = re.compile(r"(\d{6})")
_DIRECT_REF_PREFIX = "self-hosted-direct:"
_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/135.0.0.0 Safari/537.36"
)


def _is_direct_mailbox_auth_failure(exc: Exception | None) -> bool:
    message = str(exc or "").lower()
    return (
        "http 401" in message
        or "private site password" in message
        or "please provide the password" in message
    )


def encode_direct_mailbox_ref(
    *,
    address: str,
    jwt: str,
    base_url: str = "",
    custom_auth: str = "",
) -> str:
    payload = {
        "address": str(address or "").strip(),
        "jwt": str(jwt or "").strip(),
    }
    if str(base_url or "").strip():
        payload["baseUrl"] = str(base_url).strip()
    if str(custom_auth or "").strip():
        payload["customAuth"] = str(custom_auth).strip()
    encoded = urllib.parse.quote(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), safe="")
    return f"{_DIRECT_REF_PREFIX}{encoded}"


def is_direct_mailbox_ref(
    ref: str,
    *,
    default_base_url: str = "",
    default_custom_auth: str = "",
) -> bool:
    return _decode_mailbox_ref(
        ref,
        default_base_url=default_base_url,
        default_custom_auth=default_custom_auth,
    ) is not None


def wait_direct_mailbox_code(
    *,
    mailbox_ref: str,
    default_base_url: str = "",
    default_custom_auth: str = "",
    timeout_seconds: int = 180,
    poll_interval_seconds: int = 6,
    min_mail_id: int = 0,
) -> str:
    mailbox = _decode_mailbox_ref(
        mailbox_ref,
        default_base_url=default_base_url,
        default_custom_auth=default_custom_auth,
    )
    if mailbox is None:
        raise RuntimeError("mailbox_ref is not a direct self-hosted mailbox ref")

    deadline = time.time() + max(5, int(timeout_seconds))
    interval = max(1, int(poll_interval_seconds))
    last_error: Exception | None = None

    while time.time() < deadline:
        try:
            code = _try_read_latest_code(mailbox, min_mail_id=max(0, int(min_mail_id or 0)))
            if code:
                return code
        except Exception as exc:
            last_error = exc
            if _is_direct_mailbox_auth_failure(exc):
                raise RuntimeError(f"direct mailbox auth failed: {exc}") from exc
        time.sleep(interval)

    if last_error is not None:
        raise RuntimeError(f"timeout waiting for 6-digit code: {last_error}") from last_error
    raise RuntimeError("timeout waiting for 6-digit code")


def _decode_mailbox_ref(
    ref: str,
    *,
    default_base_url: str = "",
    default_custom_auth: str = "",
) -> dict[str, str] | None:
    value = str(ref or "").strip()
    if not value:
        return None

    if value.startswith(_DIRECT_REF_PREFIX):
        payload = _decode_json_payload(value[len(_DIRECT_REF_PREFIX):])
        if payload is None:
            return None
        mailbox = _normalize_payload(payload)
        if mailbox is None:
            return None
        mailbox["base_url"] = mailbox.get("base_url") or str(default_base_url or "").strip()
        mailbox["custom_auth"] = mailbox.get("custom_auth") or str(default_custom_auth or "").strip()
        return mailbox if mailbox.get("base_url") and mailbox.get("jwt") else None

    if value.startswith("mailcreate:"):
        jwt = value.split(":", 1)[1].strip()
        base_url = str(default_base_url or "").strip()
        if not jwt or not base_url:
            return None
        return {
            "address": "",
            "jwt": jwt,
            "base_url": base_url,
            "custom_auth": str(default_custom_auth or "").strip(),
        }

    if value.startswith("self-hosted:"):
        provider_parts = value.split(":", 2)
        if len(provider_parts) == 3:
            payload = _decode_json_payload(provider_parts[2])
            if payload is None:
                return None
            mailbox = _normalize_payload(payload)
            if mailbox is None:
                return None
            mailbox["base_url"] = mailbox.get("base_url") or str(default_base_url or "").strip()
            mailbox["custom_auth"] = mailbox.get("custom_auth") or str(default_custom_auth or "").strip()
            return mailbox if mailbox.get("base_url") and mailbox.get("jwt") else None

    return None


def _decode_json_payload(encoded: str) -> dict | None:
    try:
        payload = json.loads(urllib.parse.unquote(encoded))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _normalize_payload(payload: dict) -> dict[str, str] | None:
    address = str(payload.get("address") or "").strip()
    jwt = str(payload.get("jwt") or "").strip()
    if not jwt:
        return None
    return {
        "address": address,
        "jwt": jwt,
        "base_url": str(payload.get("baseUrl") or payload.get("base_url") or "").strip(),
        "custom_auth": str(payload.get("customAuth") or payload.get("custom_auth") or "").strip(),
    }


def _request_json(
    *,
    base_url: str,
    path: str,
    bearer_token: str,
    custom_auth: str,
    timeout: int = 30,
) -> dict:
    request_url = f"{base_url.rstrip('/')}{path}"
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Authorization": f"Bearer {bearer_token}",
        # mail.aiaimimi.com sits behind Cloudflare and rejects Python's default
        # urllib signature with Error 1010, so mailbox polling must look like a
        # regular browser request.
        "User-Agent": _DEFAULT_USER_AGENT,
    }
    if custom_auth:
        headers["x-custom-auth"] = custom_auth

    req = urllib.request.Request(request_url, headers=headers, method="GET")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"self-hosted mailbox GET {path} failed: HTTP {exc.code}: {body[:200]}") from exc


def get_direct_mailbox_latest_id(
    *,
    mailbox_ref: str,
    default_base_url: str = "",
    default_custom_auth: str = "",
) -> int:
    mailbox = _decode_mailbox_ref(
        mailbox_ref,
        default_base_url=default_base_url,
        default_custom_auth=default_custom_auth,
    )
    if mailbox is None:
        raise RuntimeError("mailbox_ref is not a direct self-hosted mailbox ref")

    mails = _fetch_sorted_mails(mailbox)
    if not mails:
        return 0
    return max(int(mail.get("id") or 0) for mail in mails)


def _fetch_sorted_mails(mailbox: dict[str, str]) -> list[dict]:
    mails_response = _request_json(
        base_url=mailbox["base_url"],
        path="/api/mails?limit=20&offset=0",
        bearer_token=mailbox["jwt"],
        custom_auth=mailbox["custom_auth"],
    )
    items_raw = mails_response.get("results") or mails_response.get("emails") or mails_response.get("data") or []
    mails = [item for item in items_raw if isinstance(item, dict)]
    mails.sort(key=lambda item: int(item.get("id") or 0), reverse=True)
    return mails


def _try_read_latest_code(mailbox: dict[str, str], *, min_mail_id: int = 0) -> str | None:
    mails = _fetch_sorted_mails(mailbox)

    for mail in mails:
        mail_id = int(mail.get("id") or 0)
        if mail_id <= max(0, int(min_mail_id or 0)):
            continue

        subject_code = _extract_code_candidate(str(mail.get("subject") or ""))
        if subject_code:
            return subject_code

        if mail_id <= 0:
            continue

        detail = _request_json(
            base_url=mailbox["base_url"],
            path=f"/api/mail/{urllib.parse.quote(str(mail_id), safe='')}",
            bearer_token=mailbox["jwt"],
            custom_auth=mailbox["custom_auth"],
        )
        raw = str(detail.get("raw") or "")
        raw_code = _extract_code_candidate(raw)
        if raw_code:
            return raw_code

    return None


def _extract_code_candidate(value: str) -> str | None:
    if not value:
        return None

    candidates = [value, value.replace("=\r\n", "").replace("=\n", "")]
    try:
        decoded = quopri.decodestring(candidates[-1].encode("utf-8", errors="ignore")).decode("utf-8", errors="ignore")
        if decoded:
            candidates.append(decoded)
    except Exception:
        pass

    for candidate in candidates:
        title_match = _TITLE_6_RE.search(candidate)
        if title_match:
            return title_match.group(1)

        context_match = _CODE_CONTEXT_RE.search(candidate)
        if context_match:
            return context_match.group(1)

    fallback_match = _FALLBACK_6_RE.search(candidates[-1])
    if fallback_match:
        return fallback_match.group(1)

    return None
