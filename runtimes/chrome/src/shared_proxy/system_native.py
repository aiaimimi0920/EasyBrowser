from __future__ import annotations

import os
import urllib.parse
from dataclasses import dataclass


@dataclass(frozen=True)
class SystemNativeProxyDecision:
    target_url: str
    scheme: str
    host: str
    port: int
    mode: str
    proxy: str | None
    proxy_source: str | None
    bypassed_by_no_proxy: bool
    matched_no_proxy_rule: str | None
    no_proxy_raw: str | None


def env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() not in ("0", "false", "no", "off")


def normalize_proxy_env_url(value: str | None) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if "://" not in raw:
        return None
    return raw.rstrip("/")


def build_request_proxies(proxy: str | None) -> dict[str, str] | None:
    value = normalize_proxy_env_url(proxy)
    if not value:
        return None
    return {
        "http": value,
        "https": value,
    }


def mask_proxy_url(value: str | None) -> str:
    proxy = str(value or "").strip()
    if not proxy:
        return "none"
    try:
        parsed = urllib.parse.urlparse(proxy)
        netloc = parsed.netloc
        if "@" in netloc:
            creds, host = netloc.rsplit("@", 1)
            if ":" in creds:
                user, _password = creds.split(":", 1)
                netloc = f"{user}:***@{host}"
            else:
                netloc = f"***@{host}"
        sanitized = parsed._replace(netloc=netloc)
        return urllib.parse.urlunparse(sanitized)
    except Exception:
        return "[invalid-proxy-url]"


def resolve_system_native_proxy_decision(
    url: str,
    *,
    explicit_proxy: str | None = None,
) -> SystemNativeProxyDecision:
    parsed = urllib.parse.urlparse(url)
    scheme = str(parsed.scheme or "https").strip().lower() or "https"
    host = str(parsed.hostname or "").strip().lower()
    port = int(parsed.port or _default_port_for_scheme(scheme))
    no_proxy_raw = _normalize_optional_env(_read_env("NO_PROXY"))
    matched_no_proxy_rule = _match_no_proxy_rule(host, port, no_proxy_raw)
    explicit = normalize_proxy_env_url(explicit_proxy)

    if explicit:
        return SystemNativeProxyDecision(
            target_url=url,
            scheme=scheme,
            host=host,
            port=port,
            mode="explicit",
            proxy=explicit,
            proxy_source="explicit",
            bypassed_by_no_proxy=False,
            matched_no_proxy_rule=None,
            no_proxy_raw=no_proxy_raw,
        )

    if matched_no_proxy_rule:
        return SystemNativeProxyDecision(
            target_url=url,
            scheme=scheme,
            host=host,
            port=port,
            mode="direct",
            proxy=None,
            proxy_source=None,
            bypassed_by_no_proxy=True,
            matched_no_proxy_rule=matched_no_proxy_rule,
            no_proxy_raw=no_proxy_raw,
        )

    proxy, proxy_source = _resolve_system_proxy_from_env(scheme)
    if proxy:
        return SystemNativeProxyDecision(
            target_url=url,
            scheme=scheme,
            host=host,
            port=port,
            mode="system-native",
            proxy=proxy,
            proxy_source=proxy_source,
            bypassed_by_no_proxy=False,
            matched_no_proxy_rule=None,
            no_proxy_raw=no_proxy_raw,
        )

    return SystemNativeProxyDecision(
        target_url=url,
        scheme=scheme,
        host=host,
        port=port,
        mode="direct",
        proxy=None,
        proxy_source=None,
        bypassed_by_no_proxy=False,
        matched_no_proxy_rule=None,
        no_proxy_raw=no_proxy_raw,
    )


def stabilize_process_proxy_env() -> dict[str, str | None]:
    http_proxy = _pick_preferred_proxy_value([
        os.environ.get("HTTP_PROXY"),
        os.environ.get("http_proxy"),
        os.environ.get("ALL_PROXY"),
        os.environ.get("all_proxy"),
    ])
    https_proxy = _pick_preferred_proxy_value([
        os.environ.get("HTTPS_PROXY"),
        os.environ.get("https_proxy"),
        os.environ.get("HTTP_PROXY"),
        os.environ.get("http_proxy"),
        os.environ.get("ALL_PROXY"),
        os.environ.get("all_proxy"),
    ])
    no_proxy = _normalize_optional_env(os.environ.get("NO_PROXY") or os.environ.get("no_proxy"))

    if http_proxy:
        os.environ["HTTP_PROXY"] = http_proxy
        os.environ["http_proxy"] = http_proxy
    if https_proxy:
        os.environ["HTTPS_PROXY"] = https_proxy
        os.environ["https_proxy"] = https_proxy
    if no_proxy:
        os.environ["NO_PROXY"] = no_proxy
        os.environ["no_proxy"] = no_proxy

    return {
        "http_proxy": http_proxy,
        "https_proxy": https_proxy,
        "no_proxy": no_proxy,
    }


def debug_log_system_native_proxy_decision(
    prefix: str,
    decision: SystemNativeProxyDecision,
    *,
    enabled: bool | None = None,
    extra_fields: dict[str, str | int | bool | None] | None = None,
) -> None:
    if enabled is None:
        enabled = env_flag("DEBUG_SYSTEM_NATIVE_PROXY", False)
    if not enabled:
        return

    fields: list[tuple[str, str]] = [
        ("mode", decision.mode),
        ("target", decision.target_url or "-"),
        ("host", decision.host or "-"),
        ("scheme", decision.scheme or "-"),
        ("port", str(decision.port or 0)),
        ("proxy", mask_proxy_url(decision.proxy)),
        ("proxySource", str(decision.proxy_source or "none")),
        ("noProxyBypassed", "true" if decision.bypassed_by_no_proxy else "false"),
        ("noProxyRule", str(decision.matched_no_proxy_rule or "none")),
        ("noProxyConfigured", "true" if decision.no_proxy_raw else "false"),
    ]
    if extra_fields:
        for key, value in extra_fields.items():
            fields.append((str(key), str(value if value is not None else "none")))

    payload = " ".join(f"{key}={_quote_log_value(value)}" for key, value in fields)
    print(f"[{prefix}] system-native-route {payload}", flush=True)


def _resolve_system_proxy_from_env(scheme: str) -> tuple[str | None, str | None]:
    all_proxy = normalize_proxy_env_url(_read_env("ALL_PROXY"))
    http_proxy = normalize_proxy_env_url(_read_env("HTTP_PROXY"))
    https_proxy = normalize_proxy_env_url(_read_env("HTTPS_PROXY"))

    if scheme == "http":
        if http_proxy:
            return http_proxy, "http"
        if all_proxy:
            return all_proxy, "all"
        return None, None

    if scheme == "https":
        if https_proxy:
            return https_proxy, "https"
        if http_proxy:
            return http_proxy, "http"
        if all_proxy:
            return all_proxy, "all"
        return None, None

    for proxy_value, source in (
        (https_proxy, "https"),
        (http_proxy, "http"),
        (all_proxy, "all"),
    ):
        if proxy_value:
            return proxy_value, source
    return None, None


def _pick_preferred_proxy_value(candidates: list[str | None]) -> str | None:
    best_value: str | None = None
    best_score = -1
    for raw in candidates:
        value = normalize_proxy_env_url(raw)
        if not value:
            continue
        score = _proxy_value_score(value)
        if score > best_score:
            best_value = value
            best_score = score
    return best_value


def _proxy_value_score(value: str) -> int:
    normalized = normalize_proxy_env_url(value)
    if not normalized:
        return -1
    try:
        parsed = urllib.parse.urlparse(normalized)
        host = str(parsed.hostname or "").strip().lower()
    except Exception:
        host = ""

    score = 100
    if host in ("host.docker.internal", "gateway.docker.internal"):
        score += 300
    elif host in ("127.0.0.1", "localhost", "::1"):
        score += 0
    elif host:
        score += 150
    return score


def _read_env(name: str) -> str | None:
    return _normalize_optional_env(os.environ.get(name) or os.environ.get(name.lower()))


def _normalize_optional_env(value: str | None) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _default_port_for_scheme(scheme: str) -> int:
    if scheme == "http":
        return 80
    if scheme == "https":
        return 443
    return 0


def _match_no_proxy_rule(host: str, port: int, no_proxy_raw: str | None) -> str | None:
    target_host = str(host or "").strip().lower().rstrip(".")
    if not target_host or not no_proxy_raw:
        return None

    for raw_rule in no_proxy_raw.split(","):
        rule = str(raw_rule or "").strip()
        if not rule:
            continue
        if rule == "*":
            return rule

        rule_host, rule_port = _split_no_proxy_rule(rule)
        if not rule_host:
            continue
        if rule_port is not None and rule_port != port:
            continue

        normalized_rule_host = rule_host.lstrip(".").lower().rstrip(".")
        if not normalized_rule_host:
            continue
        if target_host == normalized_rule_host or target_host.endswith(f".{normalized_rule_host}"):
            return rule

    return None


def _split_no_proxy_rule(rule: str) -> tuple[str, int | None]:
    candidate = str(rule or "").strip()
    if not candidate or candidate == "*":
        return candidate, None
    if "://" in candidate:
        parsed = urllib.parse.urlparse(candidate)
        host = str(parsed.hostname or "").strip()
        port = parsed.port
        return host, port
    if candidate.count(":") == 1:
        host, raw_port = candidate.rsplit(":", 1)
        if raw_port.isdigit():
            return host.strip(), int(raw_port)
    return candidate, None


def _quote_log_value(value: str) -> str:
    if not value:
        return "\"\""
    if any(ch.isspace() for ch in value) or any(ch in value for ch in "\"'="):
        escaped = value.replace("\\", "\\\\").replace("\"", "\\\"")
        return f"\"{escaped}\""
    return value
