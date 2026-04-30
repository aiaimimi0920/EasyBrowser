from __future__ import annotations

import concurrent.futures
import os
import random
import threading
import time
from typing import Any, Callable


def run_service_main(
    *,
    DATA_DIR: str,
    ERROR_DIRNAME: str,
    INSTANCE_ID: str,
    CODEX_AUTH_DIRNAME: str,
    WAIT_UPDATE_DIRNAME: str,
    NEED_FIX_AUTH_DIRNAME: str,
    FIXED_SUCCESS_DIRNAME: str,
    FIXED_FAIL_DIRNAME: str,
    RESULTS_SHARD_SIZE: int,
    ENABLE_PROBE: int,
    ENABLE_REPAIRER: int,
    results_dir_fn: Callable[[], str],
    data_path_fn: Callable[..., str],
    migrate_legacy_results_layout_fn: Callable[[], None],
    probe_loop_fn: Callable[[], None],
    repairer_loop_fn: Callable[[], None],
    summary_loop_fn: Callable[[], None],
    worker_fn: Callable[[int], Any],
) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)

    os.makedirs(results_dir_fn(), exist_ok=True)

    os.makedirs(data_path_fn(CODEX_AUTH_DIRNAME), exist_ok=True)
    os.makedirs(data_path_fn(WAIT_UPDATE_DIRNAME), exist_ok=True)
    os.makedirs(data_path_fn(NEED_FIX_AUTH_DIRNAME), exist_ok=True)
    os.makedirs(data_path_fn(FIXED_SUCCESS_DIRNAME), exist_ok=True)
    os.makedirs(data_path_fn(FIXED_FAIL_DIRNAME), exist_ok=True)

    migrate_legacy_results_layout_fn()

    proxy_file = data_path_fn('proxies.txt')
    if not os.path.exists(proxy_file):
        with open(proxy_file, "w", encoding="utf-8") as f:
            f.write("# 在此文件中添加您的代理IP池，每行一个\n")
            f.write("# 格式示例: http://192.168.1.100:8080\n")

    concurrency = int(os.environ.get("CONCURRENCY", "1"))
    if concurrency < 0:
        concurrency = 0

    if ENABLE_PROBE == 1:
        try:
            t = threading.Thread(target=probe_loop_fn, name="probe_loop", daemon=True)
            t.start()
        except Exception as e:
            print(f"[probe] failed to start probe thread: {e}")

    if ENABLE_REPAIRER == 1:
        try:
            t2 = threading.Thread(target=repairer_loop_fn, name="repairer_loop", daemon=True)
            t2.start()
        except Exception as e:
            print(f"[repairer] failed to start repairer thread: {e}")

    print(f"==== 守护进程启动: 无限循环多线程生成器 (并发数: {concurrency}) ====")
    print(f"INSTANCE_ID={INSTANCE_ID}")
    print(f"results 分片将写入 {results_dir_fn()} (每 {RESULTS_SHARD_SIZE} 条一片)")
    print(f"账号 JSON 将写入 {data_path_fn(CODEX_AUTH_DIRNAME)} 并复制到 {data_path_fn(WAIT_UPDATE_DIRNAME)}")
    print(f"代理池请直接写入 {proxy_file}")

    t_summary = threading.Thread(target=summary_loop_fn, name="browser_summary", daemon=True)
    t_summary.start()

    if concurrency > 0:
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
            for i in range(concurrency):
                executor.submit(worker_fn, i + 1)
                stagger_min = float(os.environ.get("STARTUP_STAGGER_MIN_SECONDS", "0") or "0")
                stagger_max = float(os.environ.get("STARTUP_STAGGER_MAX_SECONDS", "1") or "1")
                if stagger_max < stagger_min:
                    stagger_max = stagger_min
                time.sleep(random.uniform(stagger_min, stagger_max))
    else:
        while True:
            time.sleep(3600)
