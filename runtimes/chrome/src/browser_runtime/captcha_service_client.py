from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


CaptchaProviderKind = str


@dataclass(frozen=True)
class CaptchaServiceConfig:
    kind: CaptchaProviderKind
    base_url: str
    api_key: str | None
    client_key: str | None
    timeout_seconds: int
    poll_interval_seconds: float
    max_wait_seconds: int


def _clean_optional(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text or None


def _normalize_provider_kind(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in ("turnstile_solver_camoufox", "turnstile-solver", "turnstile_solver", "camoufox"):
        return "turnstile-solver-camoufox"
    if normalized in ("yescaptcha", "ohmycaptcha", "turnstile-solver-camoufox"):
        return normalized
    fallback = _clean_optional(os.environ.get("DEFAULT_CAPTCHA_PROVIDER"))
    if fallback:
        return _normalize_provider_kind(fallback)
    return "turnstile-solver-camoufox"


def _resolve_provider_env(kind: str) -> tuple[str, str]:
    prefix = {
        "yescaptcha": "YESCAPTCHA",
        "ohmycaptcha": "OHMYCAPTCHA",
        "turnstile-solver-camoufox": "TURNSTILE_SOLVER",
    }.get(kind, "CAPTCHA_SERVICE")
    return prefix, "CAPTCHA_SERVICE"


def _resolve_default_base_url(kind: str) -> str:
    if kind == "yescaptcha":
        return "https://api.yescaptcha.com"
    if kind == "ohmycaptcha":
        return "https://api.ohmycaptcha.com"
    return "http://127.0.0.1:9876"


def get_captcha_service_config(provider_kind: str | None = None) -> CaptchaServiceConfig | None:
    kind = _normalize_provider_kind(provider_kind)
    prefix, fallback_prefix = _resolve_provider_env(kind)
    base_url = _clean_optional(
        os.environ.get(f"{prefix}_BASE_URL")
        or os.environ.get(f"{fallback_prefix}_BASE_URL")
    ) or _resolve_default_base_url(kind)
    if not base_url:
        return None
    api_key = _clean_optional(
        os.environ.get(f"{prefix}_API_KEY")
        or os.environ.get(f"{fallback_prefix}_API_KEY")
    )
    client_key = _clean_optional(
        os.environ.get(f"{prefix}_CLIENT_KEY")
        or os.environ.get(f"{fallback_prefix}_CLIENT_KEY")
    )
    timeout_seconds = int(
        _clean_optional(
            os.environ.get(f"{prefix}_TIMEOUT_SECONDS")
            or os.environ.get(f"{fallback_prefix}_TIMEOUT_SECONDS")
        ) or "30"
    )
    poll_interval_seconds = float(
        _clean_optional(
            os.environ.get(f"{prefix}_POLL_INTERVAL_SECONDS")
            or os.environ.get("CAPTCHA_SERVICE_POLL_INTERVAL_SECONDS")
        ) or "2.5"
    )
    max_wait_seconds = int(
        _clean_optional(
            os.environ.get(f"{prefix}_MAX_WAIT_SECONDS")
            or os.environ.get("CAPTCHA_SERVICE_MAX_WAIT_SECONDS")
        ) or "120"
    )
    return CaptchaServiceConfig(
        kind=kind,
        base_url=base_url.rstrip("/"),
        api_key=api_key,
        client_key=client_key,
        timeout_seconds=max(1, timeout_seconds),
        poll_interval_seconds=max(0.25, poll_interval_seconds),
        max_wait_seconds=max(5, max_wait_seconds),
    )


def list_captcha_service_configs() -> list[CaptchaServiceConfig]:
    configs: list[CaptchaServiceConfig] = []
    for kind in ("yescaptcha", "ohmycaptcha", "turnstile-solver-camoufox"):
        config = get_captcha_service_config(kind)
        if config is not None:
            configs.append(config)
    return configs


def describe_captcha_service(provider_kind: str | None = None) -> dict[str, Any]:
    config = get_captcha_service_config(provider_kind)
    if config is None:
        return {
            "configured": False,
            "kind": _normalize_provider_kind(provider_kind),
            "baseUrl": None,
            "clientKeyConfigured": False,
            "apiKeyConfigured": False,
            "timeoutSeconds": None,
            "pollIntervalSeconds": None,
            "maxWaitSeconds": None,
        }
    return {
        "configured": True,
        "kind": config.kind,
        "baseUrl": config.base_url,
        "clientKeyConfigured": bool(config.client_key),
        "apiKeyConfigured": bool(config.api_key),
        "timeoutSeconds": config.timeout_seconds,
        "pollIntervalSeconds": config.poll_interval_seconds,
        "maxWaitSeconds": config.max_wait_seconds,
    }


def describe_captcha_services() -> dict[str, Any]:
    configs = list_captcha_service_configs()
    default_kind = _normalize_provider_kind(None)
    return {
        "defaultKind": default_kind,
        "providers": {config.kind: describe_captcha_service(config.kind) for config in configs},
    }


def create_task(*, task: dict[str, Any], client_key: str | None = None, provider_kind: str | None = None) -> dict[str, Any]:
    config = get_captcha_service_config(provider_kind)
    if config is None:
        raise RuntimeError("captcha provider is not configured")
    payload: dict[str, Any] = {"task": task}
    resolved_client_key = _clean_optional(client_key) or config.client_key
    if resolved_client_key:
        payload["clientKey"] = resolved_client_key
    return _post_json(config, "/createTask", payload)


def get_task_result(*, task_id: str | int, client_key: str | None = None, provider_kind: str | None = None) -> dict[str, Any]:
    config = get_captcha_service_config(provider_kind)
    if config is None:
        raise RuntimeError("captcha provider is not configured")
    payload: dict[str, Any] = {"taskId": task_id}
    resolved_client_key = _clean_optional(client_key) or config.client_key
    if resolved_client_key:
        payload["clientKey"] = resolved_client_key
    return _post_json(config, "/getTaskResult", payload)


def get_balance(*, client_key: str | None = None, provider_kind: str | None = None) -> dict[str, Any]:
    config = get_captcha_service_config(provider_kind)
    if config is None:
        raise RuntimeError("captcha provider is not configured")
    payload: dict[str, Any] = {}
    resolved_client_key = _clean_optional(client_key) or config.client_key
    if resolved_client_key:
        payload["clientKey"] = resolved_client_key
    return _post_json(config, "/getBalance", payload)


def health_check(provider_kind: str | None = None) -> dict[str, Any]:
    config = get_captcha_service_config(provider_kind)
    if config is None:
        return {"ok": False, "error": "provider_not_configured", "provider": _normalize_provider_kind(provider_kind)}
    return _get_json(config, "/api/v1/health")


def solve_turnstile_token(
    *,
    website_url: str,
    website_key: str,
    provider_kind: str | None = None,
    proxy: str | None = None,
    action: str | None = None,
    c_data: str | None = None,
    user_agent: str | None = None,
) -> dict[str, Any]:
    kind = _normalize_provider_kind(provider_kind)
    task: dict[str, Any] = {
        "type": "TurnstileTaskProxyless",
        "websiteURL": website_url,
        "websiteKey": website_key,
    }
    if action:
        task["action"] = action
    if c_data:
        task["cData"] = c_data
    if user_agent:
        task["userAgent"] = user_agent
    if proxy:
        parsed = urllib.parse.urlparse(proxy)
        if kind == "turnstile-solver-camoufox":
            task["type"] = "TurnstileTaskCamoufox"
            task["proxy"] = proxy
        elif parsed.hostname and parsed.port:
            task["type"] = "TurnstileTask"
            task["proxyType"] = (parsed.scheme or "http").lower()
            task["proxyAddress"] = parsed.hostname
            task["proxyPort"] = parsed.port
            if parsed.username:
                task["proxyLogin"] = urllib.parse.unquote(parsed.username)
            if parsed.password:
                task["proxyPassword"] = urllib.parse.unquote(parsed.password)
    create_response = create_task(task=task, provider_kind=kind)
    error_id = int(create_response.get("errorId") or 0)
    if error_id != 0:
        raise RuntimeError(f"captcha provider createTask failed: {create_response}")
    task_id = create_response.get("taskId")
    if not task_id:
        raise RuntimeError(f"captcha provider createTask missing taskId: {create_response}")
    config = get_captcha_service_config(kind)
    assert config is not None
    deadline = time.time() + config.max_wait_seconds
    last_response: dict[str, Any] | None = None
    while time.time() < deadline:
        time.sleep(config.poll_interval_seconds)
        result = get_task_result(task_id=task_id, provider_kind=kind)
        last_response = result
        if int(result.get("errorId") or 0) != 0:
            raise RuntimeError(f"captcha provider getTaskResult failed: {result}")
        if str(result.get("status") or "").strip().lower() == "ready":
            solution = result.get("solution")
            if not isinstance(solution, dict):
                raise RuntimeError(f"captcha provider returned invalid solution: {result}")
            token = _clean_optional(
                solution.get("token")
                or solution.get("gRecaptchaResponse")
                or solution.get("cf-turnstile-response")
            )
            if not token:
                raise RuntimeError(f"captcha provider ready response missing token: {result}")
            return {
                "provider": kind,
                "taskId": task_id,
                "token": token,
                "solution": solution,
            }
    raise RuntimeError(f"captcha provider task timeout after {config.max_wait_seconds}s: {last_response or {'taskId': task_id}}")


def _headers(config: CaptchaServiceConfig) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"
    return headers


def _post_json(config: CaptchaServiceConfig, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        config.base_url + path,
        data=data,
        headers=_headers(config),
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=config.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"captcha service POST {path} failed: HTTP {exc.code}: {body[:300]}") from exc


def _get_json(config: CaptchaServiceConfig, path: str) -> dict[str, Any]:
    req = urllib.request.Request(
        config.base_url + path,
        headers=_headers(config),
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=config.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"captcha service GET {path} failed: HTTP {exc.code}: {body[:300]}") from exc
