from __future__ import annotations

from typing import Callable


def get_email(*, proxy: str | None = None, create_temp_mailbox_fn: Callable[[], tuple[str, str]]) -> tuple[str, str]:
    _ = proxy
    return create_temp_mailbox_fn()


def get_oai_code(*, address_jwt: str, timeout_seconds: int = 180, proxy: str | None = None, wait_openai_code_fn: Callable[..., str]) -> str:
    _ = proxy
    return wait_openai_code_fn(address_jwt=address_jwt, timeout_seconds=timeout_seconds)
