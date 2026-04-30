from __future__ import annotations

import os
import shutil
from typing import Any, Callable

from shared_auth import persist_named_auth_json


def list_recent_auth_files(*, limit: int, data_path: Callable[..., str], codex_auth_dirname: str) -> list[str]:
    codex_auth_dir = data_path(codex_auth_dirname)
    try:
        names = [
            os.path.join(codex_auth_dir, n)
            for n in os.listdir(codex_auth_dir)
            if n.lower().endswith('.json') and os.path.isfile(os.path.join(codex_auth_dir, n))
        ]
    except Exception:
        return []

    try:
        names.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    except Exception:
        pass

    if limit > 0:
        return names[:limit]
    return names


def sync_codex_auth_copy(*, src_path: str, codex_auth_sync_dir: str) -> None:
    if not codex_auth_sync_dir:
        return
    try:
        os.makedirs(codex_auth_sync_dir, exist_ok=True)
    except Exception:
        return

    try:
        dst = os.path.join(codex_auth_sync_dir, os.path.basename(src_path))
        shutil.copy2(src_path, dst)
    except Exception:
        pass


def sync_codex_auth_delete(*, filename: str, codex_auth_sync_dir: str) -> None:
    if not codex_auth_sync_dir:
        return
    try:
        p = os.path.join(codex_auth_sync_dir, filename)
        if os.path.isfile(p):
            os.remove(p)
    except Exception:
        pass


def write_auth_obj_to_codex_auth(
    *,
    auth_obj: Any,
    prefix: str = 'topup',
    infer_account_id_from_auth: Callable[[Any], str | None],
    data_path: Callable[..., str],
    codex_auth_dirname: str,
    instance_id: str,
    sync_codex_auth_copy_fn: Callable[..., None],
) -> str | None:
    if not isinstance(auth_obj, (dict, list, str, int, float, bool)) and auth_obj is not None:
        pass

    acc_id = infer_account_id_from_auth(auth_obj) or "unknown"
    try:
        persisted = persist_named_auth_json(
            auth_obj=auth_obj,
            data_dir=data_path(),
            instance_id=instance_id,
            primary_dirname=codex_auth_dirname,
            mirror_dirname=None,
            filename_parts=("codex", prefix, acc_id),
            sync_copy_fn=lambda src_path: sync_codex_auth_copy_fn(src_path=src_path),
        )
        return persisted.auth_path
    except Exception as e:
        print(f'[probe] write topup auth failed: {e}')
        return None
