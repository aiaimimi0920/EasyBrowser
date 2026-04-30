from __future__ import annotations

import os
import shutil
import time
from typing import Any, Callable


def run_probe_loop(
    *,
    PROBE_INTERVAL_SECONDS: int,
    TARGET_POOL_SIZE: int,
    TRIGGER_INVALID_THRESHOLD: int,
    PROBE_LOCAL_COOLDOWN_MAX_SECONDS: int,
    TOPUP_COOLDOWN_SECONDS: int,
    WAIT_UPDATE_DIRNAME: str,
    CODEX_AUTH_DIRNAME: str,
    write_lock: Any,
    ProbeResult: Any,
    _list_recent_auth_files: Callable[..., list[str]],
    _read_json: Callable[..., Any],
    _infer_account_id_from_auth: Callable[..., str | None],
    _sha256_hex_str: Callable[[str], str],
    _utc_now_iso: Callable[[], str],
    _probe_wham_one: Callable[..., Any],
    _report_probe_to_server: Callable[..., None],
    _topup_from_server: Callable[..., list[dict[str, Any]]],
    _write_auth_obj_to_codex_auth: Callable[..., str | None],
    _data_path: Callable[..., str],
    _sync_codex_auth_delete: Callable[..., None],
) -> None:



    if PROBE_INTERVAL_SECONDS < 5:



        interval = 5



    else:



        interval = PROBE_INTERVAL_SECONDS







    max_files = int(os.environ.get("PROBE_MAX_FILES", str(TARGET_POOL_SIZE)))



    if max_files <= 0:



        max_files = TARGET_POOL_SIZE







    probe_proxy = (os.environ.get("PROBE_PROXY") or "").strip() or None







    copy_topup_to_wait_update = int(os.environ.get("TOPUP_COPY_TO_WAIT_UPDATE", "0"))







    last_topup_at = 0.0



    cooldown_until_by_account: dict[str, float] = {}







    print(



        f"[probe] enabled=1 interval={interval}s max_files={max_files} target_pool={TARGET_POOL_SIZE} invalid_threshold={TRIGGER_INVALID_THRESHOLD}"



    )







    while True:



        try:



            paths = _list_recent_auth_files(limit=max_files)



            if not paths:



                time.sleep(interval)



                continue







            reports_for_probe: list[dict[str, Any]] = []



            reports_for_topup: list[dict[str, Any]] = []



            invalid_paths: list[tuple[str, str]] = []  # (file_name, abs_path)



            invalid_like = 0







            for p in paths:



                name = os.path.basename(p)



                try:



                    auth_obj = _read_json(p)



                except Exception:



                    continue







                account_id = _infer_account_id_from_auth(auth_obj)



                if not account_id:



                    continue







                email_hash = _sha256_hex_str(account_id)







                now_ts = time.time()



                cd_until = float(cooldown_until_by_account.get(account_id) or 0.0)



                if cd_until > now_ts:



                    retry_after = int(max(0, cd_until - now_ts))



                    result = ProbeResult(



                        status_code=429,



                        note="local_cooldown",



                        category="cooldown_local",



                        retry_after_seconds=retry_after,



                        http_status=None,



                    )



                else:



                    result = _probe_wham_one(auth_obj=auth_obj, proxy=probe_proxy)



                    if result.retry_after_seconds > 0:



                        wait_seconds = result.retry_after_seconds



                        if PROBE_LOCAL_COOLDOWN_MAX_SECONDS > 0:



                            wait_seconds = min(wait_seconds, PROBE_LOCAL_COOLDOWN_MAX_SECONDS)



                        cooldown_until_by_account[account_id] = time.time() + max(0, wait_seconds)







                status_code = result.status_code



                note = result.note







                it: dict[str, Any] = {



                    "email_hash": email_hash,



                    "account_id": account_id,



                    "probed_at": _utc_now_iso(),



                    "probe_category": result.category,



                    "probe_note": result.note,



                }



                if status_code is not None:



                    it["status_code"] = int(status_code)



                if result.retry_after_seconds > 0:



                    it["retry_after_seconds"] = int(result.retry_after_seconds)



                if result.http_status is not None:



                    it["upstream_status"] = int(result.http_status)







                # report probe (no file_name field)



                reports_for_probe.append(it)







                # topup wants file_name for audit only



                it2 = dict(it)



                it2["file_name"] = name



                reports_for_topup.append(it2)







                if status_code in (401, 429):



                    invalid_like += 1



                    if result.category != "cooldown_local":



                        invalid_paths.append((name, p))







                # minimal local log



                if status_code is not None and status_code != 200:



                    print(f"[probe] {name} -> {status_code} ({note}) cat={result.category} retry={result.retry_after_seconds}s")







            healthy_count = sum(1 for r in reports_for_probe if int(r.get("status_code") or 0) == 200)



            pool_size = min(TARGET_POOL_SIZE, healthy_count)



            need_topup = pool_size < TARGET_POOL_SIZE







            if need_topup and invalid_like > 0:



                reports_bad = [



                    r



                    for r in reports_for_probe



                    if int(r.get("status_code") or 0) in (401, 429)



                ]



                _report_probe_to_server(reports=reports_bad)







            now_ts = time.time()



            if need_topup and (now_ts - last_topup_at >= TOPUP_COOLDOWN_SECONDS):



                print(f"[probe] triggering topup: pool={pool_size} invalid_like={invalid_like} probed={len(reports_for_probe)}")



                got = _topup_from_server(reports=reports_for_topup)







                if got:



                    # 回灌 + 删除失效：拿到 N 个 replacement，则删除 N 个失效文件。



                    # 说明：服务端也会基于同逻辑校验并决定下发数量；本地按下发数量删除。



                    del_count = min(len(got), len(invalid_paths))







                    with write_lock:



                        # 1) 写入 replacement



                        for item in got:



                            auth_json = item.get("auth_json")



                            if auth_json is None:



                                continue



                            out_path = _write_auth_obj_to_codex_auth(auth_obj=auth_json, prefix="topup")



                            if out_path and copy_topup_to_wait_update == 1:



                                try:



                                    wait_update_dir = _data_path(WAIT_UPDATE_DIRNAME)



                                    os.makedirs(wait_update_dir, exist_ok=True)



                                    shutil.copy2(out_path, os.path.join(wait_update_dir, os.path.basename(out_path)))



                                except Exception:



                                    pass







                        # 2) 删除被替换的失效文件（及同步目录）



                        for (fname, fpath) in invalid_paths[:del_count]:



                            try:



                                # 仅允许删除 codex_auth 目录下的文件



                                codex_auth_dir = os.path.abspath(_data_path(CODEX_AUTH_DIRNAME))



                                ap = os.path.abspath(fpath)



                                if ap.startswith(codex_auth_dir + os.sep) and os.path.isfile(ap):



                                    os.remove(ap)



                                    _sync_codex_auth_delete(filename=fname)



                            except Exception:



                                pass







                    print(f"[probe] topup received={len(got)} deleted_invalid={del_count}")



                else:



                    print("[probe] topup received=0")







                last_topup_at = now_ts







        except Exception as e:



            print(f"[probe] loop error: {e}")







        time.sleep(interval)








