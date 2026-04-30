from __future__ import annotations

import json
import os
import shutil
import time
from typing import Any, Callable


def repairer_dirs(
    *,
    data_path: Callable[..., str],
    need_fix_auth_dirname: str,
    fixed_success_dirname: str,
    fixed_fail_dirname: str,
) -> tuple[str, str, str, str]:
    need = data_path(need_fix_auth_dirname)
    proc = os.path.join(need, '_processing')
    okd = data_path(fixed_success_dirname)
    bad = data_path(fixed_fail_dirname)
    return need, proc, okd, bad


def repairer_results_dir(*, results_dir: Callable[[], str]) -> str:
    return results_dir()


def append_jsonl(path: str, obj: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    line = json.dumps(obj, ensure_ascii=False, separators=(',', ':'))
    with open(path, 'a', encoding='utf-8') as f:
        f.write(line + '\n')


def read_json_any(path: str) -> Any:
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def write_json_any(path: str, obj: Any) -> None:
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def deep_merge_keep_old_when_missing(old: Any, new: Any) -> Any:
    if isinstance(old, dict) and isinstance(new, dict):
        out: dict[str, Any] = dict(old)
        for k, v in new.items():
            if k in out and isinstance(out.get(k), dict) and isinstance(v, dict):
                out[k] = deep_merge_keep_old_when_missing(out.get(k), v)
            else:
                out[k] = v

        for k in ('email', 'password'):
            if k in old and (k not in new or str(new.get(k) or '').strip() == ''):
                out[k] = old.get(k)

        return out

    return new if new is not None else old


def repairer_claim_one_file(*, need_dir: str, processing_dir: str) -> str | None:
    if not os.path.isdir(need_dir):
        return None
    os.makedirs(processing_dir, exist_ok=True)

    try:
        names = [
            n
            for n in os.listdir(need_dir)
            if n.lower().endswith('.json') and os.path.isfile(os.path.join(need_dir, n))
        ]
    except Exception:
        return None

    if not names:
        return None

    try:
        names.sort(key=lambda n: os.path.getmtime(os.path.join(need_dir, n)))
    except Exception:
        pass

    for name in names:
        src = os.path.join(need_dir, name)
        dst = os.path.join(processing_dir, name)
        try:
            os.replace(src, dst)
            return dst
        except FileNotFoundError:
            continue
        except PermissionError:
            continue
        except OSError:
            continue

    return None


def repairer_release_stale_processing(*, processing_dir: str, retry_dir: str, stale_seconds: int = 1800) -> None:
    if not os.path.isdir(processing_dir):
        return

    now = time.time()
    for name in os.listdir(processing_dir):
        if not name.lower().endswith('.json'):
            continue
        path = os.path.join(processing_dir, name)
        try:
            st = os.stat(path)
        except Exception:
            continue
        if now - st.st_mtime < stale_seconds:
            continue

        try:
            os.replace(path, os.path.join(retry_dir, name))
        except Exception:
            pass


def repairer_restore_claimed_for_test(*, claimed: str, name: str, retry_dir: str) -> None:
    try:
        dst = os.path.join(retry_dir, name)
        os.replace(claimed, dst)
    except Exception:
        try:
            shutil.copy2(claimed, os.path.join(retry_dir, name))
        except Exception:
            pass
        try:
            os.remove(claimed)
        except Exception:
            pass
