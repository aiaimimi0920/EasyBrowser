from __future__ import annotations

import os
import time
from typing import Any, Callable


def trim_ts(*, now_ts: float, rolling_window_seconds: int, success_ts: Any, attempt_ts: Any) -> None:
    cutoff = now_ts - float(rolling_window_seconds)
    while success_ts and success_ts[0] < cutoff:
        success_ts.popleft()
    while attempt_ts and attempt_ts[0] < cutoff:
        attempt_ts.popleft()


def stats_inc(
    *,
    kind: str,
    err: Exception | str | None,
    stage: str | None,
    stats_lock: Any,
    stats_dict: dict[str, Any],
    success_ts: Any,
    attempt_ts: Any,
    rolling_window_seconds: int,
    trim_ts_fn: Callable[..., None],
    flow_totals_inc_fn: Callable[..., None],
) -> None:
    with stats_lock:
        now_ts = time.time()
        if kind == 'attempt':
            stats_dict['attempt'] = int(stats_dict.get('attempt', 0)) + 1
            attempt_ts.append(now_ts)
            trim_ts_fn(now_ts=now_ts, rolling_window_seconds=rolling_window_seconds, success_ts=success_ts, attempt_ts=attempt_ts)
            return
        if kind == 'success':
            stats_dict['success'] = int(stats_dict.get('success', 0)) + 1
            success_ts.append(now_ts)
            trim_ts_fn(now_ts=now_ts, rolling_window_seconds=rolling_window_seconds, success_ts=success_ts, attempt_ts=attempt_ts)
            flow_totals_inc_fn('browser', 1)
            return
        stats_dict['fail'] = int(stats_dict.get('fail', 0)) + 1
        if kind in stats_dict:
            stats_dict[kind] = int(stats_dict.get(kind, 0)) + 1
        else:
            stats_dict['other'] = int(stats_dict.get('other', 0)) + 1
        if err is not None:
            stats_dict['last_error'] = str(err)
        stg = stage or 'stage_other'
        if stg in stats_dict:
            stats_dict[stg] = int(stats_dict.get(stg, 0)) + 1
        else:
            stats_dict['stage_other'] = int(stats_dict.get('stage_other', 0)) + 1


def stats_snapshot(
    *,
    stats_lock: Any,
    stats_dict: dict[str, Any],
    success_ts: Any,
    attempt_ts: Any,
    rolling_window_seconds: int,
    trim_ts_fn: Callable[..., None],
) -> dict[str, Any]:
    with stats_lock:
        now_ts = time.time()
        trim_ts_fn(now_ts=now_ts, rolling_window_seconds=rolling_window_seconds, success_ts=success_ts, attempt_ts=attempt_ts)
        st = dict(stats_dict)
        st['rolling_success'] = len(success_ts)
        st['rolling_attempt'] = len(attempt_ts)
        st['rolling_window_seconds'] = rolling_window_seconds
        return st


def event_log_path(*, results_dir_value: str) -> str:
    return os.path.join(results_dir_value, 'browser_events.jsonl')


def record_event(
    *,
    event: str,
    fields: dict[str, Any],
    utc_now_iso_fn: Callable[[], str],
    instance_id: str,
    write_lock: Any,
    append_jsonl_fn: Callable[..., None],
    event_log_path_value: str,
) -> None:
    try:
        payload = {'ts': utc_now_iso_fn(), 'event': event, 'instance': instance_id}
        payload.update(fields)
        with write_lock:
            append_jsonl_fn(event_log_path_value, payload)
    except Exception:
        pass


def summary_loop(
    *,
    summary_print_seconds: int,
    stats_snapshot_fn: Callable[[], dict[str, Any]],
    run_started_at: float,
    rolling_window_seconds: int,
    flow_totals_snapshot_fn: Callable[[], tuple[int, int]],
) -> None:
    while True:
        time.sleep(summary_print_seconds)
        st = stats_snapshot_fn()
        elapsed = max(1.0, time.time() - run_started_at)
        speed_h = float(st.get('success', 0)) * 3600.0 / elapsed
        rw = max(1, int(st.get('rolling_window_seconds', rolling_window_seconds)))
        rolling_success = int(st.get('rolling_success', 0) or 0)
        rolling_attempt = int(st.get('rolling_attempt', 0) or 0)
        rolling_h = rolling_success * 3600.0 / float(rw)
        rolling_sr = (rolling_success / float(rolling_attempt)) if rolling_attempt > 0 else 0.0
        protocol_total, browser_total = flow_totals_snapshot_fn()
        print(
            (
                f"[BROWSER_SUMMARY] 完成 {st.get('success', 0)} | 尝试 {st.get('attempt', 0)} | 失败 {st.get('fail', 0)} "
                f"| blocked {st.get('blocked', 0)} | otp_timeout {st.get('otp_timeout', 0)} | proxy_error {st.get('proxy_error', 0)} "
                f"| 阶段(email/pwd/otp/profile/callback/other)="
                f"{st.get('stage_email', 0)}/{st.get('stage_password', 0)}/{st.get('stage_otp', 0)}/"
                f"{st.get('stage_profile', 0)}/{st.get('stage_callback', 0)}/{st.get('stage_other', 0)} "
                f"| 速度(累计){speed_h:.0f}/h | 速度({rw}s){rolling_h:.0f}/h | 成功率({rw}s){rolling_sr*100:.1f}%"
                f" | 总生成(协议/浏览器) {protocol_total}/{browser_total}"
            ),
            flush=True,
        )
