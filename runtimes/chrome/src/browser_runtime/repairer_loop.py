from __future__ import annotations

import os
import random
import time
from typing import Any, Callable


def run_repairer_loop(
    *,
    repairer_dirs: Callable[[], tuple[str, str, str, str]],
    repairer_results_dir: Callable[[], str],
    repairer_release_stale_processing: Callable[..., None],
    repairer_claim_one_file: Callable[[], str | None],
    repairer_restore_claimed_for_test: Callable[..., None],
    load_proxies: Callable[[], list[str]],
    repair_one_auth_file: Callable[..., tuple[bool, str, str | None]],
    append_jsonl: Callable[..., None],
    utc_now_iso: Callable[[], str],
    read_json_any: Callable[[str], Any],
    report_auth_repair_failed: Callable[..., tuple[bool, int, str]],
    repairer_poll_seconds: float,
    repairer_test_keep_input: int,
) -> None:
    need, proc, okd, bad = repairer_dirs()
    os.makedirs(need, exist_ok=True)
    os.makedirs(proc, exist_ok=True)
    os.makedirs(okd, exist_ok=True)
    os.makedirs(bad, exist_ok=True)
    os.makedirs(repairer_results_dir(), exist_ok=True)

    print(f"[repairer] enabled=1 need_fix_dir={need}")
    print(f"[repairer] poll_seconds={repairer_poll_seconds}")
    print(f"[repairer] test_keep_input={repairer_test_keep_input}")

    stale_seconds = int(os.environ.get('REPAIRER_STALE_SECONDS', '1800'))
    processed_once_in_test: set[str] = set()

    while True:
        try:
            repairer_release_stale_processing(stale_seconds=stale_seconds)

            claimed = repairer_claim_one_file()
            if not claimed:
                time.sleep(repairer_poll_seconds)
                continue

            name = os.path.basename(claimed)

            if repairer_test_keep_input == 1 and name in processed_once_in_test:
                repairer_restore_claimed_for_test(claimed=claimed, name=name)
                time.sleep(repairer_poll_seconds)
                continue

            proxies = load_proxies()
            proxy = random.choice(proxies) if proxies else None

            ok = False
            out_path = None
            reason = ''
            try:
                ok, reason, out_path = repair_one_auth_file(claimed, proxy=proxy)
            except Exception as e:
                ok = False
                reason = f'exception:{e}'

            if ok:
                try:
                    if repairer_test_keep_input == 1:
                        repairer_restore_claimed_for_test(claimed=claimed, name=name)
                        processed_once_in_test.add(name)
                    else:
                        os.remove(claimed)
                except Exception:
                    pass
                print(f"[repairer] ok file={name} out={out_path}")
                continue

            if 'no_quota_for_otp' in (reason or ''):
                append_jsonl(
                    os.path.join(repairer_results_dir(), 'repairer_no_quota.jsonl'),
                    {'ts': utc_now_iso(), 'file': name, 'reason': reason},
                )
                try:
                    if repairer_test_keep_input == 1:
                        repairer_restore_claimed_for_test(claimed=claimed, name=name)
                        processed_once_in_test.add(name)
                    else:
                        os.remove(claimed)
                except Exception:
                    pass
                print(f"[repairer] skip(no_quota) file={name}")
                continue

            try:
                auth_obj = read_json_any(claimed)
            except Exception:
                auth_obj = {}

            acc = ''
            try:
                acc = str(auth_obj.get('account_id') or '').strip() if isinstance(auth_obj, dict) else ''
            except Exception:
                acc = ''
            if not acc:
                try:
                    acc = str((auth_obj.get('https://api.openai.com/auth') or {}).get('chatgpt_account_id') or '').strip() if isinstance(auth_obj, dict) else ''
                except Exception:
                    acc = ''

            report_ok = False
            report_http = 0
            report_resp = ''
            if acc:
                try:
                    report_ok, report_http, report_resp = report_auth_repair_failed(account_id=acc, note=reason[:1000])
                except Exception as e:
                    report_ok, report_http, report_resp = False, 0, f'exception:{e}'

            append_jsonl(
                os.path.join(repairer_results_dir(), 'repairer_failed.jsonl'),
                {
                    'ts': utc_now_iso(),
                    'file': name,
                    'account_id': acc,
                    'reason': reason,
                    'report_ok': report_ok,
                    'http': report_http,
                    'resp': str(report_resp or '')[:800],
                },
            )

            try:
                if repairer_test_keep_input == 1:
                    repairer_restore_claimed_for_test(claimed=claimed, name=name)
                    processed_once_in_test.add(name)
                else:
                    os.remove(claimed)
            except Exception:
                pass

            print(f"[repairer] fail file={name} reason={reason} report_ok={report_ok} http={report_http}")

        except Exception as e:
            print(f"[repairer] loop error: {e}")

        time.sleep(0.2)
