from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

from shared_mailbox.cloudflare_temp_email_client import encode_direct_mailbox_ref


def repair_one_auth_file(
    path: str,
    *,
    proxy: str | None,
    read_json_any: Callable[[str], Any],
    platformtools_dev_vars: dict[str, Any],
    mailcreate_cfg: dict[str, Any],
    mailcreate_base_url: str,
    append_jsonl: Callable[..., None],
    repairer_results_dir: Callable[[], str],
    utc_now_iso: Callable[[], str],
    probe_wham_one: Callable[..., Any],
    probe_result_factory: Callable[..., Any],
    driver_init_lock: Any,
    new_driver: Callable[..., tuple[Any, str | None]],
    generate_oauth_url: Callable[[], Any],
    repairer_drive_login_and_get_callback_url: Callable[..., tuple[str, str]],
    submit_callback_url: Callable[..., tuple[str, str]],
    deep_merge_keep_old_when_missing: Callable[[Any, Any], Any],
    instance_id: str,
    data_path: Callable[..., str],
    fixed_success_dirname: str,
    write_lock: Any,
    write_json_any: Callable[[str, Any], None],
) -> tuple[bool, str, str | None]:
    """Repair one auth json file.

    Returns:
      (ok, reason, out_path)
    """

    name = os.path.basename(path)
    auth_obj = read_json_any(path)

    if not isinstance(auth_obj, dict):
        return False, "invalid_json_not_object", None

    email = str(auth_obj.get("email") or "").strip()
    password = str(auth_obj.get("password") or "").strip()
    account_id = str(auth_obj.get("account_id") or "").strip()

    if not account_id:
        # fallback from nested claims field
        try:
            account_id = str((auth_obj.get("https://api.openai.com/auth") or {}).get("chatgpt_account_id") or "").strip()
        except Exception:
            account_id = ""

    if not email:
        return False, "missing_email", None
    if not password:
        return False, "missing_password", None

    # Prepare mailbox_ref candidates (encoded refs for mailbox_provider)
    candidates: list[str] = []

    # 1) previously persisted mailbox_ref (from our own submit_callback_url)
    mr0 = str(auth_obj.get("mailbox_ref") or "").strip()
    if mr0:
        candidates.append(mr0)

    # 2) best-effort: mint self-hosted direct mailbox ref for existing address (preferred for repair)
    # If admin creds exist, we can poll the self-hosted mailbox runtime reliably.

    # 3) best-effort: if user provides self-hosted admin creds, they can mint a direct ref for an existing address
    # (Optional; errors ignored.)
    try:
        mc_custom = (
            os.environ.get("MAILCREATE_CUSTOM_AUTH")
            or platformtools_dev_vars.get("MAILCREATE_CUSTOM_AUTH")
            or str(mailcreate_cfg.get("MAILCREATE_CUSTOM_AUTH") or "")
            or ""
        ).strip()
        mc_admin = (
            os.environ.get("MAILCREATE_ADMIN_AUTH")
            or platformtools_dev_vars.get("MAILCREATE_ADMIN_AUTH")
            or str(mailcreate_cfg.get("MAILCREATE_ADMIN_AUTH") or "")
            or ""
        ).strip()
        if mc_custom and mc_admin and str(mailcreate_base_url or "").strip():
            # admin endpoints
            base = str(mailcreate_base_url).strip().rstrip("/")

            def _http_json(*, url: str, method: str = "GET", headers: dict[str, str] | None = None, payload: Any | None = None, timeout: int = 30) -> tuple[int, str, Any]:
                hdr = dict(headers or {})
                data = None
                if payload is not None:
                    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                    hdr.setdefault("Content-Type", "application/json")
                req = urllib.request.Request(url, data=data, headers=hdr, method=method)
                try:
                    with urllib.request.urlopen(req, timeout=timeout) as resp:
                        st = int(getattr(resp, "status", 200))
                        text = resp.read().decode("utf-8", errors="replace")
                        try:
                            obj = json.loads(text) if text else {}
                        except Exception:
                            obj = {}
                        return st, text, obj
                except urllib.error.HTTPError as e:
                    text = e.read().decode("utf-8", errors="replace")
                    try:
                        obj = json.loads(text) if text else {}
                    except Exception:
                        obj = {}
                    return int(getattr(e, "code", 0) or 0), text, obj

            admin_headers = {"x-custom-auth": mc_custom, "x-admin-auth": mc_admin, "Accept": "application/json"}
            q = urllib.parse.urlencode({"limit": "50", "offset": "0", "query": email})
            st1, _tx1, obj1 = _http_json(url=f"{base}/admin/address?{q}", method="GET", headers=admin_headers)
            addr_id = None
            if 200 <= st1 < 300 and isinstance(obj1, dict) and isinstance(obj1.get("results"), list):
                target = email.strip().lower()
                for it in obj1.get("results"):
                    if isinstance(it, dict) and str(it.get("name") or "").strip().lower() == target:
                        try:
                            addr_id = int(it.get("id"))
                        except Exception:
                            addr_id = None
                        break

            if addr_id:
                st2, _tx2, obj2 = _http_json(url=f"{base}/admin/show_password/{int(addr_id)}", method="GET", headers=admin_headers)
                if 200 <= st2 < 300 and isinstance(obj2, dict):
                    jwt = str(obj2.get("jwt") or "").strip()
                    if jwt:
                        candidates.append(
                            encode_direct_mailbox_ref(
                                address=email,
                                jwt=jwt,
                                base_url=base,
                                custom_auth=mc_custom,
                            )
                        )
    except Exception:
        pass

    # 4) last resort: try gptmail by email
    candidates.append(f"gptmail:{email}")

    # de-dup candidates, keep order
    seen: set[str] = set()
    candidates = [c for c in candidates if c and (c not in seen and not seen.add(c))]

    # probe for log (optional)
    try:
        result = probe_wham_one(auth_obj=auth_obj, proxy=None)
    except Exception:
        result = probe_result_factory(status_code=None, note="probe_failed", category="probe_failed")

    append_jsonl(
        os.path.join(repairer_results_dir(), "repairer_probe.jsonl"),
        {
            "ts": utc_now_iso(),
            "file": name,
            "account_id": account_id,
            "email": email,
            "status_code": result.status_code,
            "note": result.note,
            "probe_category": result.category,
            "retry_after_seconds": result.retry_after_seconds,
            "upstream_status": result.http_status,
        },
    )

    driver = None
    proxy_dir = None
    try:
        with driver_init_lock:
            driver, proxy_dir = new_driver(proxy)

        oauth = generate_oauth_url()
        callback_url, chosen_ref = repairer_drive_login_and_get_callback_url(
            driver=driver,
            oauth=oauth,
            email=email,
            password=password,
            mailbox_ref_candidates=candidates,
        )

        # exchange callback -> new token json
        reg_email, config_json = submit_callback_url(
            callback_url=callback_url,
            expected_state=oauth.state,
            code_verifier=oauth.code_verifier,
            redirect_uri=oauth.redirect_uri,
            proxy=proxy,
            mailbox_ref=(chosen_ref or (mr0 or "")),
            password=password,
            first_name=str(auth_obj.get("first_name") or ""),
            last_name=str(auth_obj.get("last_name") or ""),
            birthdate=str(auth_obj.get("birthdate") or ""),
        )

        try:
            new_obj = json.loads(config_json)
        except Exception:
            new_obj = {}

        merged = deep_merge_keep_old_when_missing(auth_obj, new_obj)

        # Write outputs
        # 约定：修缮成功后不写入本地 token 池（禁止进入 codex_auth）。
        # 成功产物只进入 fixed_success，后续由 uploader 负责上传 fixed_success 目录。
        ts_ms = int(time.time() * 1000)
        rand = secrets.token_hex(3)
        safe_acc = re.sub(r"[^a-zA-Z0-9_.-]+", "_", (account_id or "unknown"))[:64] or "unknown"
        out_name = f"codex-repaired-{safe_acc}-{instance_id}-{ts_ms}-{rand}.json"

        fixed_success_path = os.path.join(data_path(fixed_success_dirname), out_name)

        with write_lock:
            os.makedirs(data_path(fixed_success_dirname), exist_ok=True)
            write_json_any(fixed_success_path, merged)

        append_jsonl(
            os.path.join(repairer_results_dir(), "repairer_success.jsonl"),
            {"ts": utc_now_iso(), "file": name, "account_id": account_id, "email": reg_email, "out": out_name},
        )

        return True, "ok", fixed_success_path

    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
        if proxy_dir and os.path.exists(proxy_dir):
            try:
                shutil.rmtree(proxy_dir, ignore_errors=True)
            except Exception:
                pass



