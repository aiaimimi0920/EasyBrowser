from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import socket
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence


DEFAULT_CODEX_AUTH_DIRNAME = "codex_auth"
DEFAULT_WAIT_UPDATE_DIRNAME = "wait_update"


@dataclass(frozen=True)
class AuthStorageSettings:
    data_dir: str
    instance_id: str
    codex_auth_dirname: str = DEFAULT_CODEX_AUTH_DIRNAME
    wait_update_dirname: str = DEFAULT_WAIT_UPDATE_DIRNAME


@dataclass(frozen=True)
class AuthPersistenceResult:
    auth_path: str
    wait_update_path: str | None = None


def sanitize_instance_id(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "default"
    normalized = re.sub(r"[^a-zA-Z0-9_.-]+", "_", raw)
    return normalized[:64] or "default"


def resolve_auth_storage_settings(
    *,
    default_data_dir: str,
    env: Mapping[str, str] | None = None,
) -> AuthStorageSettings:
    env_map = env if env is not None else os.environ
    data_dir = str(env_map.get("DATA_DIR") or default_data_dir or "").strip() or default_data_dir
    instance_id = sanitize_instance_id(
        str(
            env_map.get("INSTANCE_ID")
            or env_map.get("RESULTS_INSTANCE_ID")
            or env_map.get("HOSTNAME")
            or socket.gethostname()
        )
    )
    codex_auth_dirname = (
        str(env_map.get("CODEX_AUTH_DIRNAME") or DEFAULT_CODEX_AUTH_DIRNAME).strip()
        or DEFAULT_CODEX_AUTH_DIRNAME
    )
    wait_update_dirname = (
        str(env_map.get("WAIT_UPDATE_DIRNAME") or DEFAULT_WAIT_UPDATE_DIRNAME).strip()
        or DEFAULT_WAIT_UPDATE_DIRNAME
    )
    return AuthStorageSettings(
        data_dir=data_dir,
        instance_id=instance_id,
        codex_auth_dirname=codex_auth_dirname,
        wait_update_dirname=wait_update_dirname,
    )


def _safe_name_fragment(value: str, *, default: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return default
    normalized = re.sub(r"[^a-zA-Z0-9@._+-]+", "_", raw)
    normalized = normalized.strip("._-")
    return normalized[:160] or default


def _normalize_json_payload(payload: Any) -> Any:
    if isinstance(payload, str):
        text = payload.strip()
        if not text:
            return ""
        try:
            return json.loads(text)
        except Exception:
            return payload
    return payload


def persist_named_auth_json(
    *,
    auth_obj: Any,
    data_dir: str,
    instance_id: str,
    primary_dirname: str = DEFAULT_CODEX_AUTH_DIRNAME,
    mirror_dirname: str | None = DEFAULT_WAIT_UPDATE_DIRNAME,
    filename_parts: Sequence[str],
    sync_copy_fn: Callable[[str], None] | None = None,
) -> AuthPersistenceResult:
    safe_parts = [_safe_name_fragment(part, default="unknown") for part in filename_parts if str(part or "").strip()]
    if not safe_parts:
        safe_parts = ["codex"]

    primary_dir = os.path.join(data_dir, primary_dirname)
    os.makedirs(primary_dir, exist_ok=True)

    ts_ms = int(time.time() * 1000)
    rand = secrets.token_hex(3)
    filename = f"{'-'.join(safe_parts)}-{sanitize_instance_id(instance_id)}-{ts_ms}-{rand}.json"
    auth_path = os.path.join(primary_dir, filename)

    payload = _normalize_json_payload(auth_obj)
    with open(auth_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    if sync_copy_fn is not None:
        try:
            sync_copy_fn(auth_path)
        except Exception:
            pass

    wait_update_path: str | None = None
    if mirror_dirname:
        mirror_dir = os.path.join(data_dir, mirror_dirname)
        os.makedirs(mirror_dir, exist_ok=True)
        wait_update_path = os.path.join(mirror_dir, filename)
        try:
            shutil.copy2(auth_path, wait_update_path)
        except Exception:
            wait_update_path = None

    return AuthPersistenceResult(
        auth_path=auth_path,
        wait_update_path=wait_update_path,
    )


def persist_register_success_auth(
    *,
    reg_email: str,
    auth_obj: Any,
    data_dir: str,
    instance_id: str,
    codex_auth_dirname: str = DEFAULT_CODEX_AUTH_DIRNAME,
    wait_update_dirname: str = DEFAULT_WAIT_UPDATE_DIRNAME,
    sync_copy_fn: Callable[[str], None] | None = None,
) -> AuthPersistenceResult:
    return persist_named_auth_json(
        auth_obj=auth_obj,
        data_dir=data_dir,
        instance_id=instance_id,
        primary_dirname=codex_auth_dirname,
        mirror_dirname=wait_update_dirname,
        filename_parts=("codex", reg_email, "free"),
        sync_copy_fn=sync_copy_fn,
    )
