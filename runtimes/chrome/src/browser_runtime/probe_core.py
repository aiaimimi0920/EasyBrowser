from __future__ import annotations

import json
import time
import urllib.error
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class ProbeResult:
    status_code: int | None
    note: str
    category: str
    retry_after_seconds: int = 0
    http_status: int | None = None


def infer_account_id_from_auth(auth_obj: Any) -> str | None:
    if not isinstance(auth_obj, dict):
        return None
    v = str(auth_obj.get('account_id') or '').strip()
    if v:
        return v
    auth_claims = auth_obj.get('https://api.openai.com/auth')
    if isinstance(auth_claims, dict):
        v2 = str(auth_claims.get('chatgpt_account_id') or '').strip()
        if v2:
            return v2
    return None


def infer_access_token_from_auth(auth_obj: Any) -> str | None:
    if not isinstance(auth_obj, dict):
        return None
    v = str(auth_obj.get('access_token') or '').strip()
    return v or None


def wham_headers(*, access_token: str, account_id: str) -> dict[str, str]:
    return {
        'Authorization': f'Bearer {access_token}',
        'chatgpt-account-id': account_id,
        'Accept': 'application/json',
        'originator': 'codex_cli_rs',
    }


def parse_retry_after_seconds_from_error_body(*, http_status: int, raw_body: str, now_ts: float | None = None) -> int:
    if http_status != 429:
        return 0
    now = float(now_ts if now_ts is not None else time.time())
    try:
        obj = json.loads(raw_body) if raw_body else {}
    except Exception:
        obj = {}
    if not isinstance(obj, dict):
        return 0
    err = obj.get('error')
    if not isinstance(err, dict):
        return 0
    et = str(err.get('type') or '').strip()
    if et and et != 'usage_limit_reached':
        return 0
    try:
        resets_at = int(err.get('resets_at') or 0)
    except Exception:
        resets_at = 0
    if resets_at > 0:
        wait = int(max(0, resets_at - int(now)))
        if wait > 0:
            return wait
    try:
        resets_in = int(err.get('resets_in_seconds') or 0)
    except Exception:
        resets_in = 0
    if resets_in > 0:
        return resets_in
    return 0


def extract_retry_after_seconds_from_wham_obj(obj: Any) -> int:
    if not isinstance(obj, dict):
        return 0
    rl = obj.get('rate_limit')
    if isinstance(rl, dict):
        for k in ('resets_in_seconds', 'retry_after_seconds', 'retry_after'):
            try:
                v = int(rl.get(k) or 0)
            except Exception:
                v = 0
            if v > 0:
                return v
        for k in ('resets_at', 'reset_at'):
            try:
                ts = int(rl.get(k) or 0)
            except Exception:
                ts = 0
            if ts > 0:
                wait = int(max(0, ts - int(time.time())))
                if wait > 0:
                    return wait
    for k in ('resets_in_seconds', 'retry_after_seconds', 'retry_after'):
        try:
            v = int(obj.get(k) or 0)
        except Exception:
            v = 0
        if v > 0:
            return v
    return 0


def wham_usage_is_quota0(obj: Any) -> bool:
    if not isinstance(obj, dict):
        return False
    rl = obj.get('rate_limit')
    if isinstance(rl, dict):
        allowed = rl.get('allowed')
        if allowed is False:
            return True
        limit_reached = rl.get('limit_reached')
        if limit_reached is True:
            return True
        pw = rl.get('primary_window')
        if isinstance(pw, dict):
            try:
                used_percent = pw.get('used_percent')
                if used_percent is not None and float(used_percent) >= 100:
                    return True
            except Exception:
                pass
    for k in ('allowed', 'limit_reached', 'is_available'):
        if k in obj and obj.get(k) in (False, 0):
            return True
    return False


def probe_wham_one(*, auth_obj: Any, proxy: str | None = None, get_fn: Callable[..., tuple[str, dict]], wham_usage_url: str) -> ProbeResult:
    account_id = infer_account_id_from_auth(auth_obj)
    access_token = infer_access_token_from_auth(auth_obj)
    if not account_id or not access_token:
        return ProbeResult(status_code=None, note='missing account_id/access_token', category='invalid_input')
    headers = wham_headers(access_token=access_token, account_id=account_id)
    try:
        raw, _hdr = get_fn(wham_usage_url, headers=headers, proxy=proxy)
    except urllib.error.HTTPError as e:
        code = int(getattr(e, 'code', 0) or 0)
        body = ''
        try:
            body = e.read().decode('utf-8', errors='replace')
        except Exception:
            body = ''
        if code == 401:
            return ProbeResult(status_code=401, note='http401', category='invalid_auth', http_status=401)
        if code == 429:
            retry_after = parse_retry_after_seconds_from_error_body(http_status=429, raw_body=body)
            return ProbeResult(status_code=429, note='http429', category='quota_limited', retry_after_seconds=retry_after, http_status=429)
        return ProbeResult(status_code=None, note=f'http{code}', category='upstream_http_error', http_status=code)
    except Exception as e:
        return ProbeResult(status_code=None, note=f'error:{e}', category='network_error')

    try:
        obj = json.loads(raw) if raw else {}
    except Exception:
        obj = {}

    if wham_usage_is_quota0(obj):
        retry_after = extract_retry_after_seconds_from_wham_obj(obj)
        return ProbeResult(status_code=429, note='quota0', category='quota_limited', retry_after_seconds=retry_after, http_status=200)

    return ProbeResult(status_code=200, note='ok', category='ok', http_status=200)
