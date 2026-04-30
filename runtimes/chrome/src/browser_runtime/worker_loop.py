from __future__ import annotations

import os
import random
import time
import traceback
from typing import Callable

from selenium.common.exceptions import TimeoutException


def run_worker_loop(
    worker_id: int,
    *,
    max_attempts_per_worker: int,
    require_proxy: bool,
    codex_auth_dirname: str,
    wait_update_dirname: str,
    load_proxies_fn: Callable[[], list[str]],
    pick_proxy_fn: Callable[..., tuple[str | None, float]],
    stats_inc_fn: Callable[..., None],
    record_event_fn: Callable[..., None],
    run_register_once_fn: Callable[..., tuple[str, str]],
    persist_register_success_fn: Callable[..., None],
    proxy_mark_result_fn: Callable[..., None],
    proxy_score_get_fn: Callable[..., int],
    classify_error_fn: Callable[..., str],
    infer_stage_from_error_fn: Callable[..., str],
) -> None:
    current_proxy: str | None = None
    assigned_at = 0.0
    local_attempt = 0

    headless_v = int(os.environ.get("HEADLESS", "0") or "0")
    effective_max_attempts = max_attempts_per_worker
    if headless_v == 0 and effective_max_attempts <= 0:
        effective_max_attempts = 1

    while True:
        if effective_max_attempts > 0 and local_attempt >= effective_max_attempts:
            print(f"[Worker {worker_id}] 达到 MAX_ATTEMPTS_PER_WORKER={effective_max_attempts}，停止该 worker")
            break

        local_attempt += 1
        if effective_max_attempts > 0:
            print(f"[Worker {worker_id}] 开始第 {local_attempt}/{effective_max_attempts} 次尝试")
        else:
            print(f"[Worker {worker_id}] 开始第 {local_attempt} 次尝试")

        proxies = load_proxies_fn()
        proxy, assigned_at = pick_proxy_fn(
            proxies=proxies,
            current_proxy=current_proxy,
            assigned_at=assigned_at,
            force_direct=False,
        )
        current_proxy = proxy

        if proxy:
            print(f"[Worker {worker_id}] ---> 使用代理: {proxy} <---")
        elif require_proxy:
            print(
                f"[Worker {worker_id}] [x] register_proxy_required no_proxy_available "
                f"flow=browser headless={headless_v}"
            )
            if headless_v == 0:
                print(f"[Worker {worker_id}] 已停止：无可用代理且 REQUIRE_PROXY=1（保留现场，不再重试）")
                break
            time.sleep(1.0)
            continue
        else:
            print(f"[Worker {worker_id}] ---> 未配置可用代理，使用本地网络直连 <---")

        stats_inc_fn("attempt")
        record_event_fn("attempt", worker_id=worker_id, proxy=(proxy or "DIRECT"))

        try:
            reg_email, res = run_register_once_fn(proxy=proxy)
            persist_register_success_fn(reg_email=reg_email, res=res)
            stats_inc_fn("success")
            proxy_mark_result_fn(proxy, "success")
            record_event_fn(
                "success",
                worker_id=worker_id,
                email=reg_email,
                proxy=(proxy or "DIRECT"),
                proxy_score=proxy_score_get_fn(proxy or ""),
            )
            print(
                f"[Worker {worker_id}] [✓] 注册成功，Token 已保存在 {codex_auth_dirname} 并复制到 {wait_update_dirname}，并追加到 results 分片！"
            )
            if headless_v == 0:
                print(f"[Worker {worker_id}] 已按要求停止：保留浏览器现场，不再进入下一轮尝试")
                break
        except RuntimeError as e:
            err_cls = classify_error_fn(e)
            stg = infer_stage_from_error_fn(str(e))
            stats_inc_fn(err_cls, err=e, stage=stg)
            proxy_mark_result_fn(proxy, err_cls)
            record_event_fn(
                "fail",
                worker_id=worker_id,
                reason=str(e),
                error_class=err_cls,
                stage=stg,
                proxy=(proxy or "DIRECT"),
                proxy_score=proxy_score_get_fn(proxy or ""),
            )
            print(f"[Worker {worker_id}] [x] {e}")
            if headless_v == 0:
                print(f"[Worker {worker_id}] 已按要求停止：保留浏览器现场，不再进入下一轮尝试")
                break
        except TimeoutException as e:
            err_cls = classify_error_fn(e)
            stg = infer_stage_from_error_fn(str(e))
            stats_inc_fn(err_cls, err=e, stage=stg)
            proxy_mark_result_fn(proxy, err_cls)
            record_event_fn(
                "fail",
                worker_id=worker_id,
                reason=str(e),
                error_class=err_cls,
                stage=stg,
                proxy=(proxy or "DIRECT"),
                proxy_score=proxy_score_get_fn(proxy or ""),
            )
            print(f"[Worker {worker_id}] [x] 页面加载超时，可能遇到风控盾拦截。")
            if headless_v == 0:
                print(f"[Worker {worker_id}] 已按要求停止：保留浏览器现场，不再进入下一轮尝试")
                break
        except Exception as e:
            err_str = str(e)
            err_cls = classify_error_fn(e)
            stg = infer_stage_from_error_fn(err_str)
            stats_inc_fn(err_cls, err=e, stage=stg)
            proxy_mark_result_fn(proxy, err_cls)
            record_event_fn(
                "fail",
                worker_id=worker_id,
                reason=err_str,
                error_class=err_cls,
                stage=stg,
                proxy=(proxy or "DIRECT"),
                proxy_score=proxy_score_get_fn(proxy or ""),
            )
            if (
                "RemoteDisconnected" in err_str
                or "Connection aborted" in err_str
                or "Max retries exceeded" in err_str
                or "UNEXPECTED_EOF_WHILE_READING" in err_str
                or "UNEXPECTED_MESSAGE" in err_str
            ):
                print(f"[Worker {worker_id}] [x] 代理连接强制中断 (SSL/EOF断流)")
            else:
                trace_str = traceback.format_exc()
                print(f"[Worker {worker_id}] [x] 本次注册流程意外中止:\n{trace_str}")
            if headless_v == 0:
                print(f"[Worker {worker_id}] 已按要求停止：保留浏览器现场，不再进入下一轮尝试")
                break

        sleep_min = int(os.environ.get("SLEEP_MIN", "5"))
        sleep_max = int(os.environ.get("SLEEP_MAX", "20"))
        sleep_time = random.randint(sleep_min, sleep_max) if sleep_max >= sleep_min else sleep_min
        print(f"[Worker {worker_id}] 任务结束。挂起 {sleep_time} 秒后开启下一轮尝试...")
        time.sleep(sleep_time)
