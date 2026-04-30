from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Callable


def post_json_simple(*, url: str, headers: dict[str, str], payload: Any, timeout: int = 30) -> tuple[int, str]:
    data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = int(getattr(resp, 'status', 200))
            text = resp.read().decode('utf-8', errors='replace')
            return status, text
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode('utf-8', errors='replace')
        except Exception:
            body = str(exc)
        return int(getattr(exc, 'code', 0) or 0), body


def refill_url(path: str, *, refill_server_url: str) -> str:
    base = (refill_server_url or '').strip().rstrip('/')
    if not base:
        return ''
    return base + path


def report_auth_repair_failed(
    *,
    account_id: str,
    note: str = 'auth_fix_failed',
    refill_server_url: str,
    refill_upload_key: str,
    post_json_simple_fn: Callable[..., tuple[int, str]],
) -> tuple[bool, int, str]:
    base = (refill_server_url or '').strip().rstrip('/')
    key = (refill_upload_key or '').strip()
    if not base or not key:
        return False, 0, 'missing REFILL_SERVER_URL/REFILL_UPLOAD_KEY'

    headers = {'X-Upload-Key': key, 'Content-Type': 'application/json'}
    url = base + '/v1/auth/repairs/submit-failed'
    status, text = post_json_simple_fn(
        url=url,
        headers=headers,
        payload={'account_id': account_id, 'note': note},
        timeout=30,
    )
    if 200 <= status < 300:
        try:
            obj = json.loads(text) if text else {}
        except Exception:
            obj = {}
        if isinstance(obj, dict) and obj.get('ok') is True:
            return True, status, text[:800]
    return False, status, text[:800]


def report_probe_to_server(
    *,
    reports: list[dict[str, Any]],
    refill_server_url: str,
    refill_upload_key: str,
    refill_url_fn: Callable[[str], str],
    post_json_simple_fn: Callable[..., tuple[int, str]],
    probe_timeout_seconds: int,
) -> None:
    if not refill_server_url or not refill_upload_key:
        return
    if not reports:
        return

    url = refill_url_fn('/v1/probe-report')
    if not url:
        return

    headers = {
        'Content-Type': 'application/json',
        'X-Upload-Key': refill_upload_key,
    }
    status, text = post_json_simple_fn(url=url, headers=headers, payload={'reports': reports}, timeout=probe_timeout_seconds)
    if not (200 <= status < 300):
        print(f'[probe] probe-report failed: http={status} resp={text[:300]}')


def download_json_from_url(*, url: str, timeout: int = 30) -> Any | None:
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode('utf-8', errors='replace')
        return json.loads(raw) if raw else None
    except Exception as exc:
        print(f'[probe] download topup json failed: url={url[:180]} err={exc}')
        return None


def topup_from_server(
    *,
    reports: list[dict[str, Any]],
    refill_server_url: str,
    refill_upload_key: str,
    refill_url_fn: Callable[[str], str],
    post_json_simple_fn: Callable[..., tuple[int, str]],
    download_json_from_url_fn: Callable[..., Any | None],
    probe_timeout_seconds: int,
    target_pool_size: int,
) -> list[dict[str, Any]]:
    if not refill_server_url or not refill_upload_key:
        return []

    url = refill_url_fn('/v1/refill/topup')
    if not url:
        return []

    headers = {
        'Content-Type': 'application/json',
        'X-Upload-Key': refill_upload_key,
    }
    account_ids = [
        str(it.get('account_id') or '').strip()
        for it in reports
        if isinstance(it, dict) and str(it.get('account_id') or '').strip()
    ]
    payload = {
        'target_pool_size': target_pool_size,
        'reports': reports,
        'account_ids': account_ids,
    }
    status, text = post_json_simple_fn(url=url, headers=headers, payload=payload, timeout=probe_timeout_seconds)
    if not (200 <= status < 300):
        print(f'[probe] refill/topup failed: http={status} resp={text[:300]}')
        return []

    try:
        obj = json.loads(text) if text else {}
    except Exception:
        obj = {}

    if obj.get('ok') is not True:
        print(f'[probe] refill/topup not ok: resp={text[:300]}')
        return []

    items = obj.get('accounts')
    if not isinstance(items, list):
        return []

    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        download_url = str(item.get('download_url') or '').strip()
        if not download_url:
            continue
        auth = download_json_from_url_fn(url=download_url, timeout=probe_timeout_seconds)
        if auth is None:
            continue
        out.append({'file_name': item.get('file_name'), 'auth_json': auth})
    return out
