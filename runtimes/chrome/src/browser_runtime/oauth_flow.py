from __future__ import annotations

import base64
import hashlib
import http.cookiejar
import json
import secrets
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Any


AUTH_URL = "https://auth.openai.com/oauth/authorize"
TOKEN_URL = "https://auth.openai.com/oauth/token"
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"

DEFAULT_CALLBACK_PORT = 1455
DEFAULT_REDIRECT_URI = f"http://localhost:{DEFAULT_CALLBACK_PORT}/auth/callback"
DEFAULT_SCOPE = "openid email profile offline_access"

CHATGPT_BASE = "https://chatgpt.com"
CHATGPT_HOME_URL = f"{CHATGPT_BASE}/"
CHATGPT_LOGIN_URL = f"{CHATGPT_BASE}/auth/login"
CHATGPT_NEXTAUTH_CSRF_URL = f"{CHATGPT_BASE}/api/auth/csrf"
CHATGPT_NEXTAUTH_SIGNIN_OPENAI_URL = f"{CHATGPT_BASE}/api/auth/signin/openai"

CHATGPT_WEB_CLIENT_ID = "app_X8zY6vW2pQ9tR3dE7nK1jL5gH"
CHATGPT_WEB_AUTH_URL = "https://auth.openai.com/api/accounts/authorize"
CHATGPT_WEB_REDIRECT_URI = "https://chatgpt.com/api/auth/callback/openai"
CHATGPT_WEB_SCOPE = "openid email profile offline_access model.request model.read organization.read organization.write"
CHATGPT_WEB_SCREEN_HINT = "login_or_signup"


def _b64url_no_pad(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _sha256_b64url_no_pad(s: str) -> str:
    return _b64url_no_pad(hashlib.sha256(s.encode("ascii")).digest())


def _random_state(nbytes: int = 16) -> str:
    return secrets.token_urlsafe(nbytes)


def _pkce_verifier() -> str:
    return secrets.token_urlsafe(64)


def _parse_callback_url(callback_url: str) -> dict[str, str]:
    candidate = callback_url.strip()
    if not candidate:
        return {
            "code": "",
            "state": "",
            "error": "",
            "error_description": "",
        }

    if "://" not in candidate:
        if candidate.startswith("?"):
            candidate = f"http://localhost{candidate}"
        elif any(ch in candidate for ch in "/?#") or ":" in candidate:
            candidate = f"http://{candidate}"
        elif "=" in candidate:
            candidate = f"http://localhost/?{candidate}"

    parsed = urllib.parse.urlparse(candidate)
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    fragment = urllib.parse.parse_qs(parsed.fragment, keep_blank_values=True)

    for key, values in fragment.items():
        if key not in query or not query[key] or not (query[key][0] or "").strip():
            query[key] = values

    def get1(k: str) -> str:
        v = query.get(k, [""])
        return (v[0] or "").strip()

    code = get1("code")
    state = get1("state")
    error = get1("error")
    error_description = get1("error_description")

    if code and not state and "#" in code:
        code, state = code.split("#", 1)

    if not error and error_description:
        error, error_description = error_description, ""

    return {
        "code": code,
        "state": state,
        "error": error,
        "error_description": error_description,
    }


def _submit_callback_error(stage: str, detail: str) -> RuntimeError:
    return RuntimeError(f"submit_callback_url.{stage}: {detail}".strip())


def _jwt_claims_no_verify(id_token: str) -> dict[str, Any]:
    if not id_token or id_token.count(".") < 2:
        return {}
    payload_b64 = id_token.split(".")[1]
    pad = "=" * ((4 - (len(payload_b64) % 4)) % 4)
    try:
        payload = base64.urlsafe_b64decode((payload_b64 + pad).encode("ascii"))
        return json.loads(payload.decode("utf-8"))
    except Exception:
        return {}


def _to_int(v: Any) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _build_opener(
    proxy: str | None = None,
    *,
    verify_tls: bool = True,
    cookie_jar: http.cookiejar.CookieJar | None = None,
):
    handlers: list[Any] = []
    if cookie_jar is not None:
        handlers.append(urllib.request.HTTPCookieProcessor(cookie_jar))
    if proxy:
        handlers.append(urllib.request.ProxyHandler({'http': proxy, 'https': proxy}))
    else:
        # Disable environment proxies so the "direct" route is actually direct.
        handlers.append(urllib.request.ProxyHandler({}))
    if not verify_tls:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        handlers.append(urllib.request.HTTPSHandler(context=ctx))
    return urllib.request.build_opener(*handlers)


def _default_browser_user_agent(driver=None) -> str:
    try:
        candidate = str(driver.execute_script("return navigator.userAgent || '';") or "").strip()
        if candidate:
            return candidate.replace("HeadlessChrome/", "Chrome/")
    except Exception:
        pass
    return (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
    )


def _cookie_matches_host(cookie: http.cookiejar.Cookie, host: str) -> bool:
    cookie_domain = str(getattr(cookie, "domain", "") or "").lstrip(".").lower()
    host_lower = str(host or "").strip().lower()
    return bool(cookie_domain) and (host_lower == cookie_domain or host_lower.endswith(f".{cookie_domain}"))


def _inject_chatgpt_cookies_into_browser(
    *,
    driver,
    cookie_jar: http.cookiejar.CookieJar,
) -> None:
    driver.get(CHATGPT_LOGIN_URL)
    for cookie in cookie_jar:
        if not _cookie_matches_host(cookie, "chatgpt.com"):
            continue

        payload: dict[str, Any] = {
            "name": str(cookie.name or ""),
            "value": str(cookie.value or ""),
            "path": str(cookie.path or "/"),
            "secure": bool(cookie.secure),
        }
        if getattr(cookie, "expires", None):
            try:
                payload["expiry"] = int(cookie.expires)
            except Exception:
                pass

        same_site = None
        try:
            same_site = cookie.get_nonstandard_attr("SameSite")
        except Exception:
            same_site = None
        if same_site:
            payload["sameSite"] = str(same_site)

        try:
            driver.add_cookie(payload)
        except Exception:
            continue


def _bootstrap_chatgpt_web_oauth_in_browser(
    *,
    driver,
    proxy: str | None = None,
) -> OAuthStart:
    _ = proxy

    def _browser_fetch_json(*, url: str, method: str, body: str | None, headers: dict[str, str]) -> dict[str, Any]:
        raw_result = driver.execute_async_script(
            """
            const [url, method, body, headers, done] = arguments;
            fetch(url, {
              method,
              credentials: 'include',
              headers: headers || {},
              body: body || undefined,
            }).then(async (resp) => {
              const text = await resp.text();
              done({ ok: resp.ok, status: resp.status, text, url: resp.url });
            }).catch((err) => {
              done({ error: String(err) });
            });
            """,
            url,
            method,
            body,
            headers,
        )
        if not isinstance(raw_result, dict):
            raise RuntimeError(f"chatgpt_nextauth_fetch_invalid_result {raw_result!r}")
        if raw_result.get("error"):
            raise RuntimeError(f"chatgpt_nextauth_fetch_error {raw_result['error']}")
        status = int(raw_result.get("status") or 0)
        text = str(raw_result.get("text") or "")
        if status >= 400:
            raise RuntimeError(f"chatgpt_nextauth_fetch_status={status} body={text[:200]}")
        try:
            return json.loads(text or "{}")
        except Exception as exc:
            raise RuntimeError(f"chatgpt_nextauth_fetch_json_error {text[:200]!r}") from exc

    driver.get(CHATGPT_LOGIN_URL)
    try:
        driver.set_script_timeout(30)
    except Exception:
        pass

    csrf_payload = _browser_fetch_json(
        url=CHATGPT_NEXTAUTH_CSRF_URL,
        method="GET",
        body=None,
        headers={
            "Accept": "application/json",
        },
    )
    csrf_token = str(csrf_payload.get("csrfToken") or "").strip() if isinstance(csrf_payload, dict) else ""
    if not csrf_token:
        raise RuntimeError("chatgpt_nextauth_csrf_missing_token")

    ext_oai_did = str(uuid.uuid4())
    auth_session_logging_id = str(uuid.uuid4())
    signin_query = urllib.parse.urlencode({
        "prompt": "login",
        "screen_hint": CHATGPT_WEB_SCREEN_HINT,
        "ext-oai-did": ext_oai_did,
        "auth_session_logging_id": auth_session_logging_id,
    })
    signin_body = urllib.parse.urlencode({
        "csrfToken": csrf_token,
        "callbackUrl": CHATGPT_HOME_URL,
        "json": "true",
    })
    signin_payload = _browser_fetch_json(
        url=f"{CHATGPT_NEXTAUTH_SIGNIN_OPENAI_URL}?{signin_query}",
        method="POST",
        body=signin_body,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": CHATGPT_BASE,
            "Referer": CHATGPT_LOGIN_URL,
        },
    )
    auth_url = str(signin_payload.get("url") or "").strip() if isinstance(signin_payload, dict) else ""
    if not auth_url:
        raise RuntimeError("chatgpt_nextauth_signin_missing_url")

    parsed_auth_url = urllib.parse.urlparse(auth_url)
    auth_query = urllib.parse.parse_qs(parsed_auth_url.query, keep_blank_values=True)
    state = str((auth_query.get("state") or [""])[0] or "").strip()
    if not state:
        raise RuntimeError("chatgpt_nextauth_signin_missing_state")

    return OAuthStart(
        auth_url=auth_url,
        state=state,
        code_verifier="",
        redirect_uri=CHATGPT_WEB_REDIRECT_URI,
    )


def _post_form(
    url: str,
    data: dict[str, str],
    *,
    timeout: int = 30,
    proxy: str | None = None,
    verify_tls: bool = False,
    try_direct_first: bool = True,
    max_retries: int = 6,
) -> dict[str, Any]:
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
    )
    retry_total = max(1, max_retries)
    for attempt in range(retry_total):
        routes: list[tuple[str, str | None]] = []
        if proxy:
            if try_direct_first:
                routes.extend([("direct", None), ("proxy", proxy)])
            else:
                routes.extend([("proxy", proxy), ("direct", None)])
        else:
            routes.append(("direct", None))

        for label, route_proxy in routes:
            try:
                with _build_opener(route_proxy, verify_tls=verify_tls).open(req, timeout=timeout) as resp:
                    raw = resp.read()
                    if resp.status != 200:
                        raise RuntimeError(
                            f"token exchange failed: {resp.status}: {raw.decode('utf-8', 'replace')}"
                        )
                    return json.loads(raw.decode("utf-8"))
            except urllib.error.HTTPError as exc:
                raw = exc.read()
                raise RuntimeError(
                    f"token exchange failed: {exc.code}: {raw.decode('utf-8', 'replace')}"
                ) from exc
            except Exception:
                continue

        time.sleep(2)

    raise RuntimeError("Failed to post form after max retries")


@dataclass(frozen=True)
class OAuthStart:
    auth_url: str
    state: str
    code_verifier: str
    redirect_uri: str


def generate_oauth_url(
    *,
    redirect_uri: str = DEFAULT_REDIRECT_URI,
    scope: str = DEFAULT_SCOPE,
    auth_url: str = AUTH_URL,
    client_id: str = CLIENT_ID,
    extra_params: dict[str, str] | None = None,
    include_pkce: bool = True,
) -> OAuthStart:
    state = _random_state()
    code_verifier = _pkce_verifier() if include_pkce else ""

    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": scope,
        "state": state,
        "prompt": "login",
    }
    if include_pkce:
        params.update({
            "code_challenge": _sha256_b64url_no_pad(code_verifier),
            "code_challenge_method": "S256",
        })
    if client_id == CLIENT_ID:
        # Codex CLI 专属参数
        params.update({
            "id_token_add_organizations": "true",
            "codex_cli_simplified_flow": "true",
        })
    if extra_params:
        params.update(extra_params)

    full_auth_url = f"{auth_url}?{urllib.parse.urlencode(params)}"
    return OAuthStart(
        auth_url=full_auth_url,
        state=state,
        code_verifier=code_verifier,
        redirect_uri=redirect_uri,
    )


def generate_chatgpt_web_oauth_url(
    *,
    driver=None,
    proxy: str | None = None,
) -> OAuthStart:
    """生成用于创建账号的 ChatGPT Web 客户端 OAuth URL (不触发 phone_wall)"""
    if driver is not None:
        return _bootstrap_chatgpt_web_oauth_in_browser(driver=driver, proxy=proxy)

    device_id = str(uuid.uuid4())
    return generate_oauth_url(
        auth_url=CHATGPT_WEB_AUTH_URL,
        client_id=CHATGPT_WEB_CLIENT_ID,
        redirect_uri=CHATGPT_WEB_REDIRECT_URI,
        scope=CHATGPT_WEB_SCOPE,
        include_pkce=False,
        extra_params={
            "audience": "https://api.openai.com/v1",
            "device_id": device_id,
            "screen_hint": CHATGPT_WEB_SCREEN_HINT,
            "ext-oai-did": device_id,
            "auth_session_logging_id": str(uuid.uuid4()),
        },
    )


def validate_callback_url(*, callback_url: str, expected_state: str) -> dict[str, str]:
    cb = _parse_callback_url(callback_url)
    if cb["error"]:
        desc = cb["error_description"]
        raise _submit_callback_error("validate.oauth_error", f"{cb['error']}: {desc}".strip())

    if not cb["code"]:
        raise _submit_callback_error("validate.missing_code", "callback url missing ?code=")
    if not cb["state"]:
        raise _submit_callback_error("validate.missing_state", "callback url missing ?state=")
    if cb["state"] != expected_state:
        raise _submit_callback_error("validate.state_mismatch", "state mismatch")

    return cb


def submit_callback_url(
    *,
    callback_url: str,
    expected_state: str,
    code_verifier: str,
    redirect_uri: str = DEFAULT_REDIRECT_URI,
    proxy: str | None = None,
    mailbox_ref: str = "",
    password: str = "",
    first_name: str = "",
    last_name: str = "",
    birthdate: str = "",
    token_url: str = TOKEN_URL,
    client_id: str = CLIENT_ID,
    token_post_verify_tls: bool = False,
    token_post_try_direct_first: bool = True,
    token_post_max_retries: int = 6,
    return_metadata: bool = False,
) -> tuple[str, str] | tuple[str, str, dict[str, Any]]:
    metadata: dict[str, Any] = {
        "validateStatus": "pending",
        "tokenExchangeStatus": "pending",
        "tokenResponseStatus": "pending",
        "claimsStatus": "pending",
        "authPayloadStatus": "pending",
    }
    cb = validate_callback_url(
        callback_url=callback_url,
        expected_state=expected_state,
    )
    metadata["validateStatus"] = "ok"

    try:
        token_resp = _post_form(
            token_url,
            {
                "grant_type": "authorization_code",
                "client_id": client_id,
                "code": cb["code"],
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier,
            },
            timeout=30,
            proxy=proxy,
            verify_tls=token_post_verify_tls,
            try_direct_first=token_post_try_direct_first,
            max_retries=token_post_max_retries,
        )
        metadata["tokenExchangeStatus"] = "ok"
    except Exception as exc:
        raise _submit_callback_error("token_exchange", str(exc)) from exc

    access_token = (token_resp.get("access_token") or "").strip()
    refresh_token = (token_resp.get("refresh_token") or "").strip()
    id_token = (token_resp.get("id_token") or "").strip()
    expires_in = _to_int(token_resp.get("expires_in"))
    if not access_token:
        raise _submit_callback_error("token_response.access_token_missing", "token response missing access_token")
    if not refresh_token:
        raise _submit_callback_error("token_response.refresh_token_missing", "token response missing refresh_token")
    if not id_token:
        raise _submit_callback_error("token_response.id_token_missing", "token response missing id_token")
    metadata["tokenResponseStatus"] = "ok"

    claims = _jwt_claims_no_verify(id_token)
    if not claims:
        raise _submit_callback_error("claims.decode_failed", "failed to decode id_token claims")
    email = str(claims.get("email") or "").strip()
    if not email:
        raise _submit_callback_error("claims.email_missing", "id_token claims missing email")
    metadata["claimsStatus"] = "ok"
    metadata["email"] = email
    auth_claims = claims.get("https://api.openai.com/auth") or {}
    if not isinstance(auth_claims, dict):
        auth_claims = {}
    account_id = str(auth_claims.get("chatgpt_account_id") or "").strip()

    now = int(time.time())
    expired_rfc3339 = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(now + max(expires_in, 0))
    )
    now_rfc3339 = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))

    config = dict(claims)
    config.update({
        "type": "codex",
        "email": email,
        "expired": expired_rfc3339,
        "disabled": False,
        "id_token": id_token,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "password": password,
        "birthdate": birthdate,
        "client_id": client_id,
        "last_name": last_name,
        "account_id": account_id,
        "first_name": first_name,
        "session_id": claims.get("session_id", ""),
        "last_refresh": now_rfc3339,
        "pwd_auth_time": claims.get("pwd_auth_time", int(time.time() * 1000)),
        "https://api.openai.com/auth": auth_claims,
        "https://api.openai.com/profile": claims.get("https://api.openai.com/profile", {}),
    })

    schema_defaults = {
        "refresh_token": "",
        "session_id": "",
        "password": "",
        "birthdate": "",
        "first_name": "",
        "last_name": "",
        "mailbox_ref": "",
    }
    for key, value in schema_defaults.items():
        if key not in config:
            config[key] = value

    if mailbox_ref and str(mailbox_ref).strip():
        config["mailbox_ref"] = str(mailbox_ref).strip()

    try:
        payload = json.dumps(config, ensure_ascii=False, separators=(",", ":"))
        metadata["authPayloadStatus"] = "ok"
        if return_metadata:
            return email, payload, metadata
        return email, payload
    except Exception as exc:
        raise _submit_callback_error("auth_payload.serialize_failed", str(exc)) from exc
