from __future__ import annotations

import random
import time
from typing import Any, Callable


def proxy_is_cooled_down(*, proxy: str, now_ts: float | None, proxy_state_lock: Any, proxy_cooldown_until: dict[str, float]) -> bool:
    now_v = time.time() if now_ts is None else now_ts
    with proxy_state_lock:
        until = float(proxy_cooldown_until.get(proxy, 0.0) or 0.0)
    return until > now_v


def proxy_score_get(*, proxy: str, proxy_state_lock: Any, proxy_score: dict[str, int]) -> int:
    with proxy_state_lock:
        return int(proxy_score.get(proxy, 0) or 0)


def proxy_mark_result(
    *,
    proxy: str | None,
    cls: str,
    proxy_state_lock: Any,
    proxy_score: dict[str, int],
    proxy_cooldown_until: dict[str, float],
    cooldown_proxy_error_seconds: int,
    cooldown_blocked_seconds: int,
    cooldown_otp_timeout_seconds: int,
    cooldown_other_seconds: int,
) -> None:
    p = str(proxy or '').strip()
    if not p:
        return
    c = (cls or '').strip().lower()
    if c == 'success':
        delta, cool = 1, 0
    elif c == 'proxy_error':
        delta, cool = -2, cooldown_proxy_error_seconds
    elif c == 'blocked':
        delta, cool = -2, cooldown_blocked_seconds
    elif c == 'otp_timeout':
        delta, cool = -1, cooldown_otp_timeout_seconds
    else:
        delta, cool = -1, cooldown_other_seconds
    with proxy_state_lock:
        cur = int(proxy_score.get(p, 0) or 0)
        cur = max(-8, min(8, cur + delta))
        proxy_score[p] = cur
        if cool > 0:
            proxy_cooldown_until[p] = time.time() + float(cool)


def pick_proxy(
    *,
    proxies: list[str],
    current_proxy: str | None,
    assigned_at: float,
    force_direct: bool,
    proxy_rotate_seconds: int,
    proxy_is_cooled_down_fn: Callable[..., bool],
    proxy_score_get_fn: Callable[..., int],
) -> tuple[str | None, float]:
    now_ts = time.time()
    if force_direct:
        return None, now_ts
    if not proxies:
        return None, now_ts
    if current_proxy:
        if (
            proxy_rotate_seconds > 0
            and (now_ts - assigned_at) < proxy_rotate_seconds
            and not proxy_is_cooled_down_fn(current_proxy, now_ts)
            and current_proxy in proxies
        ):
            return current_proxy, assigned_at
    ready = [p for p in proxies if not proxy_is_cooled_down_fn(p, now_ts)]
    if not ready:
        return None, assigned_at
    if current_proxy and len(ready) > 1 and current_proxy in ready:
        ready = [p for p in ready if p != current_proxy]
    weights: list[int] = []
    for p in ready:
        s = proxy_score_get_fn(p)
        weights.append(max(1, s + 9))
    total = sum(weights)
    r = random.randint(1, total)
    acc = 0
    for p, w in zip(ready, weights):
        acc += w
        if r <= acc:
            return p, now_ts
    return ready[-1], now_ts
