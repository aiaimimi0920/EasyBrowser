from __future__ import annotations

import os
import shutil
import time
from typing import Any, Callable

from shared_auth import AuthPersistenceResult, persist_register_success_auth


def load_proxies(*, disable_proxy: bool, data_path: Callable[..., str]) -> list[str]:
    if disable_proxy:
        return []
    proxy_file = data_path('proxies.txt')
    if os.path.exists(proxy_file):
        with open(proxy_file, 'r', encoding='utf-8') as f:
            proxies = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        return proxies
    return []


def persist_register_success(
    *,
    reg_email: str,
    res: str,
    write_lock: Any,
    append_result_line: Callable[[str], None],
    data_path: Callable[..., str],
    codex_auth_dirname: str,
    wait_update_dirname: str,
    instance_id: str,
    sync_codex_auth_copy: Callable[..., None],
) -> AuthPersistenceResult:
    with write_lock:
        append_result_line(res)
        return persist_register_success_auth(
            reg_email=reg_email,
            auth_obj=res,
            data_dir=data_path(),
            instance_id=instance_id,
            codex_auth_dirname=codex_auth_dirname,
            wait_update_dirname=wait_update_dirname,
            sync_copy_fn=lambda src_path: sync_codex_auth_copy(src_path=src_path),
        )


def run_register_once(
    *,
    proxy: str | None,
    keep_open_on_fail: bool,
    driver_init_lock: Any,
    new_driver: Callable[..., tuple[Any, str | None]],
    register_fn: Callable[..., tuple[str, str]],
    max_round_retries: int = 0,
    retry_sleep_seconds: float = 0.0,
    recoverable_error_predicate: Callable[[RuntimeError], bool] | None = None,
    always_close_error_predicate: Callable[[Exception], bool] | None = None,
) -> tuple[str, str]:
    retries = max(0, int(max_round_retries))
    last_exc: Exception | None = None
    startup_retries = max(0, int(os.environ.get("BROWSER_STARTUP_RETRIES", "2") or "2"))
    startup_retry_sleep_seconds = max(
        0.0,
        float(os.environ.get("BROWSER_STARTUP_RETRY_SLEEP_SECONDS", "1.5") or "1.5"),
    )

    for round_idx in range(retries + 1):
        driver = None
        proxy_dir = None
        ok = False
        final_attempt = round_idx >= retries
        try:
            with driver_init_lock:
                for startup_attempt in range(startup_retries + 1):
                    try:
                        driver, proxy_dir = new_driver(proxy)
                        break
                    except Exception as exc:
                        last_exc = exc
                        message = str(exc or "").lower()
                        should_retry_startup = (
                            startup_attempt < startup_retries
                            and (
                                "session not created" in message
                                or "cannot connect to chrome" in message
                                or "chrome not reachable" in message
                                or "devtoolsactiveport" in message
                            )
                        )
                        if not should_retry_startup:
                            raise
                        print(
                            f"[driver] startup retry {startup_attempt + 1}/{startup_retries + 1} "
                            f"after transient launch failure: {exc}"
                        )
                        time.sleep(startup_retry_sleep_seconds)
            out = register_fn(driver, proxy)
            ok = True
            return out
        except RuntimeError as exc:
            last_exc = exc
            should_restart = bool(recoverable_error_predicate(exc)) if recoverable_error_predicate else False
            if should_restart and not final_attempt:
                print(
                    f"[recover] Recoverable register failure ({exc}), "
                    f"restarting full register round {round_idx + 1}/{retries + 1}"
                )
                try:
                    if driver:
                        driver.quit()
                except Exception:
                    pass
                if proxy_dir and os.path.exists(proxy_dir):
                    shutil.rmtree(proxy_dir, ignore_errors=True)
                time.sleep(max(0.0, retry_sleep_seconds))
                continue
            raise
        finally:
            force_close = bool(always_close_error_predicate(last_exc)) if (last_exc is not None and always_close_error_predicate) else False
            should_close = ((not keep_open_on_fail) or ok or (last_exc is not None and not final_attempt) or force_close)
            if should_close and driver:
                try:
                    driver.quit()
                except Exception:
                    pass
            elif driver:
                hold_seconds = int(os.environ.get("KEEP_BROWSER_OPEN_ON_FAIL_SECONDS", "180") or "180")
                try:
                    deadline = time.time() + max(0, hold_seconds)
                    while time.time() < deadline:
                        try:
                            _ = driver.current_url
                        except Exception:
                            break
                        time.sleep(1.0)
                except Exception:
                    pass

            if proxy_dir and os.path.exists(proxy_dir):
                shutil.rmtree(proxy_dir, ignore_errors=True)

    if last_exc is not None:
        raise last_exc
    raise RuntimeError("register round failed without explicit exception")
