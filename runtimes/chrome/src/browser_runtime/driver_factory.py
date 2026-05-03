from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import tempfile
import threading
from typing import Any, Callable

try:
    import undetected_chromedriver as uc  # type: ignore
except Exception:
    uc = None

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

from browser_runtime.camoufox_native import (
    describe_native_camoufox_executor,
    ensure_native_camoufox_profile_root,
    native_camoufox_enabled,
    native_camoufox_isolated_profile,
    prime_native_camoufox_profile,
)
from browser_runtime.cdp_sourceurl import patch_driver_sourceurl
from shared_proxy import (
    debug_log_system_native_proxy_decision,
    env_flag,
    mask_proxy_url,
    resolve_system_native_proxy_decision,
)


_uc_init_lock = threading.Lock()


def _argument_base(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    return normalized.split("=", 1)[0]


class _FilteredChromeArgumentList(list[str]):
    def __init__(
        self,
        values: list[str] | tuple[str, ...],
        *,
        blocked_bases: set[str] | None = None,
        dedupe_bases: set[str] | None = None,
    ) -> None:
        super().__init__()
        self._blocked_bases = {item.strip() for item in (blocked_bases or set()) if item.strip()}
        self._dedupe_bases = {item.strip() for item in (dedupe_bases or set()) if item.strip()}
        self.extend(values)

    def _should_skip(self, value: str) -> bool:
        normalized = str(value or "").strip()
        if not normalized:
            return True
        base = _argument_base(normalized)
        if base in self._blocked_bases:
            return True
        if base in self._dedupe_bases:
            for existing in self:
                if _argument_base(existing) == base:
                    return True
        return False

    def append(self, value: str) -> None:
        if self._should_skip(value):
            return
        super().append(str(value).strip())

    def extend(self, values) -> None:  # type: ignore[override]
        for value in values:
            self.append(value)

    def insert(self, index: int, value: str) -> None:
        if self._should_skip(value):
            return
        super().insert(index, str(value).strip())


def normalize_browser_backend(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    if normalized in ("camoufox", "firefox"):
        return "camoufox"
    return "custom"


def _remove_browser_state_path(path: str) -> bool:
    try:
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path, ignore_errors=True)
        else:
            os.remove(path)
        return True
    except FileNotFoundError:
        return False
    except Exception:
        return False


def _cleanup_stale_browser_startup_state(browser_user_data_dir: str) -> None:
    target_dir = (browser_user_data_dir or "").strip()
    if not target_dir:
        return
    if not env_flag("BROWSER_CLEAN_STALE_PROFILE_STATE", True):
        return

    removed_files: list[str] = []
    for name in (
        "SingletonLock",
        "SingletonCookie",
        "SingletonSocket",
        "DevToolsActivePort",
    ):
        full_path = os.path.join(target_dir, name)
        if _remove_browser_state_path(full_path):
            removed_files.append(name)

    killed_pids: list[int] = []
    if os.name != "nt":
        profile_flag = f"--user-data-dir={target_dir}"
        try:
            out = subprocess.check_output(
                ["ps", "-eo", "pid=,args="],
                stderr=subprocess.STDOUT,
                timeout=3,
            )
            for raw_line in out.decode("utf-8", errors="ignore").splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                pid_text, _, args = line.partition(" ")
                if not pid_text.isdigit():
                    continue
                pid = int(pid_text)
                if pid <= 1 or pid == os.getpid():
                    continue
                args_lc = args.lower()
                if "chromedriver" in args_lc:
                    try:
                        os.kill(pid, signal.SIGKILL)
                        killed_pids.append(pid)
                    except Exception:
                        pass
                    continue
                if "chrome" in args_lc and profile_flag in args:
                    try:
                        os.kill(pid, signal.SIGKILL)
                        killed_pids.append(pid)
                    except Exception:
                        pass
        except Exception:
            pass

    if removed_files or killed_pids:
        removed_text = ",".join(removed_files) if removed_files else "none"
        pid_text = ",".join(str(pid) for pid in killed_pids) if killed_pids else "none"
        print(
            f"[driver] cleaned stale browser startup state profile={target_dir} "
            f"files={removed_text} pids={pid_text}",
            flush=True,
        )


def resolve_browser_binary_path() -> str | None:
    explicit = (os.environ.get("BROWSER_BINARY_PATH") or os.environ.get("CHROME_BINARY_PATH") or "").strip()
    if explicit and os.path.exists(explicit):
        return explicit

    def _which(name: str) -> str | None:
        try:
            out = subprocess.check_output(["which", name], stderr=subprocess.STDOUT, timeout=3)
            value = out.decode("utf-8", errors="ignore").strip()
            return value or None
        except Exception:
            return None

    if os.name == "nt":
        for base in (
            os.environ.get("PROGRAMFILES"),
            os.environ.get("PROGRAMFILES(X86)"),
            os.environ.get("LOCALAPPDATA"),
        ):
            if not base:
                continue
            candidate = os.path.join(base, "Google", "Chrome", "Application", "chrome.exe")
            if os.path.exists(candidate):
                return candidate
        return None

    for command in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        candidate = _which(command)
        if candidate:
            return candidate
    return None


def resolve_camoufox_browser_binary_path() -> str | None:
    explicit = (os.environ.get("CAMOUFOX_BROWSER_BINARY_PATH") or "").strip()
    if explicit and os.path.exists(explicit):
        return explicit

    def _which(name: str) -> str | None:
        try:
            out = subprocess.check_output(["which", name], stderr=subprocess.STDOUT, timeout=3)
            value = out.decode("utf-8", errors="ignore").strip()
            return value or None
        except Exception:
            return None

    if os.name != "nt":
        for command in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable"):
            candidate = _which(command)
            if candidate:
                return candidate
    return resolve_browser_binary_path()


def _normalize_proxy_env_url(value: str) -> str | None:
    raw = (value or "").strip()
    if not raw:
        return None
    if "://" not in raw:
        return None
    return raw.rstrip("/")


def resolve_env_proxy_server() -> str | None:
    for key in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
        candidate = _normalize_proxy_env_url(os.environ.get(key) or "")
        if candidate:
            return candidate
    return None


def build_env_proxy_bypass_list() -> str:
    entries: list[str] = ["<-loopback>", "localhost", "127.0.0.1"]
    raw = (
        os.environ.get("NO_PROXY")
        or os.environ.get("no_proxy")
        or ""
    )
    for item in raw.split(","):
        value = item.strip()
        if value:
            entries.append(value)
    deduped: list[str] = []
    seen: set[str] = set()
    for item in entries:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return ";".join(deduped)


def _quote_log_value(value: str) -> str:
    if not value:
        return "\"\""
    if any(ch.isspace() for ch in value) or any(ch in value for ch in "\"'="):
        escaped = value.replace("\\", "\\\\").replace("\"", "\\\"")
        return f"\"{escaped}\""
    return value


def _debug_log_browser_system_native_proxy(*, startup_url: str, system_proxy: str | None, bypass_list: str) -> None:
    if not env_flag("DEBUG_SYSTEM_NATIVE_PROXY", False):
        return

    raw_no_proxy = (
        os.environ.get("NO_PROXY")
        or os.environ.get("no_proxy")
        or ""
    ).strip()
    target_url = (startup_url or "").strip()
    if target_url:
        decision = resolve_system_native_proxy_decision(target_url)
        debug_log_system_native_proxy_decision(
            "browser-driver",
            decision,
            extra_fields={
                "requestLabel": "browser-startup",
                "bypassList": bypass_list or "none",
            },
        )
        return

    fields = {
        "mode": "system-native" if system_proxy else "direct",
        "target": "browser-startup",
        "host": "unknown",
        "scheme": "unknown",
        "port": "0",
        "proxy": mask_proxy_url(system_proxy),
        "proxySource": "env" if system_proxy else "none",
        "noProxyBypassed": "unknown",
        "noProxyRule": "unknown",
        "noProxyConfigured": "true" if raw_no_proxy else "false",
        "requestLabel": "browser-startup",
        "bypassList": bypass_list or "none",
        "targetKnown": "false",
    }
    payload = " ".join(f"{key}={_quote_log_value(str(value))}" for key, value in fields.items())
    print(f"[browser-driver] system-native-route {payload}", flush=True)


def resolve_chromedriver_binary_path() -> str | None:
    explicit = (os.environ.get("CHROMEDRIVER_PATH") or "").strip()
    if explicit and os.path.exists(explicit):
        return explicit

    def _which(name: str) -> str | None:
        try:
            out = subprocess.check_output(["which", name], stderr=subprocess.STDOUT, timeout=3)
            value = out.decode("utf-8", errors="ignore").strip()
            return value or None
        except Exception:
            return None

    if os.name == "nt":
        for base in (
            os.environ.get("PROGRAMFILES"),
            os.environ.get("PROGRAMFILES(X86)"),
            os.environ.get("LOCALAPPDATA"),
        ):
            if not base:
                continue
            candidate = os.path.join(base, "Google", "Chrome", "Application", "chromedriver.exe")
            if os.path.exists(candidate):
                return candidate
        return None

    for candidate in ("/usr/local/bin/chromedriver", "/usr/bin/chromedriver"):
        if os.path.exists(candidate):
            return candidate
    return _which("chromedriver")


def create_proxy_extension(proxy: str, base_dir: str | None = None) -> str | None:
    match = re.search(r"http://([^:]+):([^@]+)@([^:]+):(\d+)", proxy)
    if not match:
        return None
    user, pwd, host, port = match.groups()

    manifest_json = """
    {
        "version": "1.0.0",
        "manifest_version": 2,
        "name": "Chrome Proxy",
        "permissions": [
            "proxy",
            "tabs",
            "unlimitedStorage",
            "storage",
            "<all_urls>",
            "webRequest",
            "webRequestBlocking"
        ],
        "background": {
            "scripts": ["background.js"]
        },
        "minimum_chrome_version":"22.0.0"
    }
    """

    background_js = """
    var config = {
            mode: "fixed_servers",
            rules: {
              singleProxy: {
                scheme: "http",
                host: "%s",
                port: parseInt(%s)
              },
              bypassList: ["localhost", "127.0.0.1", "<local>"]
            }
          };

    chrome.proxy.settings.set({value: config, scope: "regular"}, function() {});

    function callbackFn(details) {
        return {
            authCredentials: {
                username: "%s",
                password: "%s"
            }
        };
    }

    chrome.webRequest.onAuthRequired.addListener(
                callbackFn,
                {urls: ["<all_urls>"]},
                ['blocking']
    );
    """ % (host, port, user, pwd)

    if base_dir:
        plugin_dir = os.path.join(base_dir, "proxy_extension")
        os.makedirs(plugin_dir, exist_ok=True)
    else:
        plugin_dir = tempfile.mkdtemp(prefix="proxy_auth_")
    with open(os.path.join(plugin_dir, "manifest.json"), "w", encoding="utf-8") as f:
        f.write(manifest_json)
    with open(os.path.join(plugin_dir, "background.js"), "w", encoding="utf-8") as f:
        f.write(background_js)

    return plugin_dir


def resolve_chrome_version_main() -> int | None:
    raw = (os.environ.get("CHROME_VERSION_MAIN") or "").strip()
    if raw.isdigit():
        try:
            v = int(raw)
            if v > 0:
                return v
        except Exception:
            pass

    def _extract_major(ver: str) -> int | None:
        m = re.search(r"(\d+)\.", str(ver or "").strip())
        if not m:
            return None
        try:
            major_v = int(m.group(1))
            return major_v if major_v > 0 else None
        except Exception:
            return None

    selected_binary = resolve_browser_binary_path()
    if selected_binary:
        try:
            out = subprocess.check_output([selected_binary, "--product-version"], stderr=subprocess.STDOUT, timeout=3)
            major_v = _extract_major(out.decode("utf-8", errors="ignore"))
            if major_v:
                return major_v
        except Exception:
            try:
                out = subprocess.check_output([selected_binary, "--version"], stderr=subprocess.STDOUT, timeout=3)
                major_v = _extract_major(out.decode("utf-8", errors="ignore"))
                if major_v:
                    return major_v
            except Exception:
                pass

    if os.name == "nt":
        windows_candidates: list[str] = []
        for base in (
            os.environ.get("PROGRAMFILES"),
            os.environ.get("PROGRAMFILES(X86)"),
            os.environ.get("LOCALAPPDATA"),
        ):
            if not base:
                continue
            windows_candidates.append(os.path.join(base, "Google", "Chrome", "Application", "chrome.exe"))

        for chrome_path in windows_candidates:
            if not os.path.exists(chrome_path):
                continue
            try:
                out = subprocess.check_output([chrome_path, "--version"], stderr=subprocess.STDOUT, timeout=3)
                major_v = _extract_major(out.decode("utf-8", errors="ignore"))
                if major_v:
                    return major_v
            except Exception:
                pass
            try:
                ps_cmd = (
                    "(Get-Item -LiteralPath '"
                    + chrome_path.replace("'", "''")
                    + "').VersionInfo.ProductVersion"
                )
                out = subprocess.check_output(
                    ["powershell", "-NoProfile", "-Command", ps_cmd],
                    stderr=subprocess.STDOUT,
                    timeout=5,
                )
                major_v = _extract_major(out.decode("utf-8", errors="ignore"))
                if major_v:
                    return major_v
            except Exception:
                pass

        for reg_cmd in (
            ["reg", "query", r"HKCU\Software\Google\Chrome\BLBeacon", "/v", "version"],
            ["reg", "query", r"HKLM\Software\Google\Chrome\BLBeacon", "/v", "version"],
            ["reg", "query", r"HKLM\Software\WOW6432Node\Google\Chrome\BLBeacon", "/v", "version"],
        ):
            try:
                out = subprocess.check_output(reg_cmd, stderr=subprocess.STDOUT, timeout=3)
                major_v = _extract_major(out.decode("utf-8", errors="ignore"))
                if major_v:
                    return major_v
            except Exception:
                continue

    for cmd in (
        ["google-chrome", "--product-version"],
        ["google-chrome-stable", "--product-version"],
        ["chromium", "--product-version"],
    ):
        try:
            out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, timeout=3)
            major_v = _extract_major(out.decode("utf-8", errors="ignore"))
            if major_v:
                return major_v
        except Exception:
            continue

    return None


def detect_runtime_user_agent(
    driver,
    *,
    resolve_chrome_version_main_fn: Callable[[], int | None],
    env_flag_fn: Callable[[str, str], bool],
) -> str:
    manual = (os.environ.get("STEALTH_USER_AGENT") or "").strip()
    if manual:
        return manual

    user_agent = ""
    try:
        version_info = driver.execute_cdp_cmd("Browser.getVersion", {})
        user_agent = str(version_info.get("userAgent") or "")
    except Exception:
        user_agent = ""

    if not user_agent:
        try:
            user_agent = str(driver.execute_script("return navigator.userAgent || '';"))
        except Exception:
            user_agent = ""

    if not user_agent:
        major_version = resolve_chrome_version_main_fn() or 120
        if os.name == "nt":
            user_agent = (
                f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                f"(KHTML, like Gecko) Chrome/{major_version}.0.0.0 Safari/537.36"
            )
        else:
            user_agent = (
                f"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                f"(KHTML, like Gecko) Chrome/{major_version}.0.0.0 Safari/537.36"
            )

    user_agent = user_agent.replace("HeadlessChrome/", "Chrome/")
    if env_flag_fn("STEALTH_MASK_LINUX", "1") and "Linux" in user_agent and "Android" not in user_agent:
        user_agent = re.sub(r"\(([^)]+)\)", "(Windows NT 10.0; Win64; x64)", user_agent, count=1)
    return user_agent


def build_stealth_profile(
    driver,
    *,
    headless: int,
    detect_runtime_user_agent_fn: Callable[[Any], str],
    extract_user_agent_bits_fn: Callable[[str], dict[str, Any]],
) -> dict[str, Any]:
    locale = (os.environ.get("STEALTH_ACCEPT_LANGUAGE") or "en-US,en").strip() or "en-US,en"
    languages = [part.strip() for part in locale.split(",") if part.strip()]
    if not languages:
        languages = ["en-US", "en"]
    user_agent = detect_runtime_user_agent_fn(driver)
    ua_bits = extract_user_agent_bits_fn(user_agent)
    try:
        hardware_concurrency = int(os.environ.get("STEALTH_HARDWARE_CONCURRENCY", "") or "0")
    except Exception:
        hardware_concurrency = 0
    if hardware_concurrency <= 0:
        detected_cores = os.cpu_count() or 8
        hardware_concurrency = min(max(int(detected_cores), 4), 16)

    if ua_bits["platformName"] == "Windows":
        webgl_vendor = (os.environ.get("STEALTH_WEBGL_VENDOR") or "Intel Inc.").strip() or "Intel Inc."
        webgl_renderer = (
            os.environ.get("STEALTH_WEBGL_RENDERER")
            or "ANGLE (Intel, Intel(R) UHD Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)"
        ).strip()
    else:
        webgl_vendor = (os.environ.get("STEALTH_WEBGL_VENDOR") or "Intel Inc.").strip() or "Intel Inc."
        webgl_renderer = (os.environ.get("STEALTH_WEBGL_RENDERER") or "Intel Iris OpenGL Engine").strip()

    return {
        "userAgent": ua_bits["userAgent"],
        "acceptLanguage": locale,
        "languages": languages,
        "platformShort": ua_bits["platformShort"],
        "platformName": ua_bits["platformName"],
        "platformVersion": ua_bits["platformVersion"],
        "architecture": ua_bits["architecture"],
        "model": ua_bits["model"],
        "mobile": ua_bits["mobile"],
        "brands": ua_bits["brands"],
        "fullVersionList": ua_bits["fullVersionList"],
        "fullVersion": ua_bits["fullVersion"],
        "vendor": (os.environ.get("STEALTH_NAVIGATOR_VENDOR") or "Google Inc.").strip() or "Google Inc.",
        "hardwareConcurrency": hardware_concurrency,
        "webglVendor": webgl_vendor,
        "webglRenderer": webgl_renderer,
        "headless": bool(headless != 0),
    }


def apply_runtime_stealth(
    driver,
    *,
    headless: int,
    build_stealth_profile_fn: Callable[[Any, int], dict[str, Any]],
    build_stealth_source_fn: Callable[[dict[str, Any]], str],
) -> dict[str, Any]:
    profile = build_stealth_profile_fn(driver, headless)
    try:
        driver.execute_cdp_cmd("Network.enable", {})
    except Exception:
        pass

    override = {
        "userAgent": profile["userAgent"],
        "acceptLanguage": profile["acceptLanguage"],
        "platform": profile["platformShort"],
        "userAgentMetadata": {
            "brands": profile["brands"],
            "fullVersion": profile["fullVersion"],
            "fullVersionList": profile["fullVersionList"],
            "platform": profile["platformName"],
            "platformVersion": profile["platformVersion"],
            "architecture": profile["architecture"],
            "model": profile["model"],
            "mobile": profile["mobile"],
        },
    }
    try:
        driver.execute_cdp_cmd("Network.setUserAgentOverride", override)
    except Exception:
        pass

    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": build_stealth_source_fn(profile)
        })
    except Exception:
        pass
    return profile


def new_driver(
    proxy: str | None = None,
    *,
    browser_backend: str = "custom",
    create_proxy_extension_fn: Callable[[str, str | None], str | None],
    apply_runtime_stealth_fn: Callable[[Any, int], dict[str, Any]],
    resolve_chrome_version_main_fn: Callable[[], int | None],
    startup_user_agent: str = "",
    browser_user_data_dir: str = "",
    startup_url: str = "",
    remove_args: set[str] | None = None,
):
    resolved_backend = normalize_browser_backend(browser_backend or os.environ.get("DEFAULT_BROWSER_BACKEND"))
    cleanup_root: str | None = None
    effective_user_data_dir = str(browser_user_data_dir or "").strip()
    native_camoufox_metadata: dict[str, Any] | None = None
    native_camoufox_bootstrapped = False
    if resolved_backend == "camoufox":
        if not effective_user_data_dir and native_camoufox_isolated_profile():
            cleanup_root, effective_user_data_dir = ensure_native_camoufox_profile_root()
        if effective_user_data_dir:
            _cleanup_stale_browser_startup_state(effective_user_data_dir)
        if native_camoufox_enabled() and effective_user_data_dir:
            try:
                native_camoufox_metadata = prime_native_camoufox_profile(
                    user_data_dir=effective_user_data_dir,
                    startup_url=startup_url,
                    proxy=proxy,
                    user_agent=startup_user_agent or None,
                )
                native_camoufox_bootstrapped = True
            except Exception as exc:
                native_camoufox_metadata = {
                    "primed": False,
                    "error": str(exc),
                    "executor": describe_native_camoufox_executor(),
                }
                print(f"[camoufox-native] bootstrap failed: {exc}", flush=True)
    browser_user_data_dir = effective_user_data_dir
    options = Options()

    anonymous_mode = int(os.environ.get("ANONYMOUS_MODE", "0") or "0")
    if anonymous_mode == 1:
        options.add_argument('--incognito')

    headless = int(os.environ.get("HEADLESS", "0") or "0")
    if headless != 0:
        options.add_argument('--headless=new')

    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    window_size = str(os.environ.get("BROWSER_WINDOW_SIZE", "500,600") or "500,600")
    options.add_argument(f'--window-size={window_size}')
    desired_window_size: tuple[int, int] | None = None
    try:
        w_raw, h_raw = [x.strip() for x in window_size.split(",", 1)]
        w, h = int(w_raw), int(h_raw)
        if w > 0 and h > 0:
            desired_window_size = (w, h)
    except Exception:
        desired_window_size = None
    browser_lang = (os.environ.get("STEALTH_BROWSER_LANG") or "en-US").strip() or "en-US"
    options.add_argument(f'--lang={browser_lang}')
    if startup_user_agent:
        options.add_argument(f'--user-agent={startup_user_agent}')
    if browser_user_data_dir:
        options.add_argument(f'--user-data-dir={browser_user_data_dir}')
        options.add_argument('--profile-directory=Default')
    options.add_argument('--enable-features=NetworkService,NetworkServiceInProcess')

    options.add_argument('--disable-features=OptimizationGuideModelDownloading,OptimizationHintsFetching,OptimizationTargetPrediction,OptimizationGuideModelExecution')
    options.add_argument('--disable-background-networking')
    options.add_argument('--disable-sync')
    options.add_argument('--disable-component-update')
    options.add_argument('--disable-domain-reliability')
    options.add_argument('--disable-client-side-phishing-detection')
    options.add_argument('--disable-default-apps')
    options.add_argument('--no-default-browser-check')
    options.add_argument('--no-first-run')
    enable_bwsi = int(os.environ.get("BROWSER_ENABLE_BWSI", "1") or "1")
    if enable_bwsi == 1:
        options.add_argument('--bwsi')
    options.add_argument('--disable-search-engine-choice-screen')
    options.add_argument('--disable-signin-promo')
    options.add_argument('--disable-features=TranslateUI,ChromeSignin,ChromeSigninIntercept,SigninIntercept,SignInPromo,ImprovedSigninUI,ChromeWhatsNewUI,AutofillServerCommunication,PasswordManagerOnboarding,AccountConsistency')
    if startup_url:
        options.add_argument(startup_url)

    browser_binary = resolve_camoufox_browser_binary_path() if resolved_backend == "camoufox" else resolve_browser_binary_path()
    if browser_binary:
        options.binary_location = browser_binary
    if resolved_backend == "camoufox":
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        options.add_argument("--disable-features=IsolateOrigins,site-per-process")
        options.add_argument("--disable-site-isolation-trials")
        options.add_argument("--disable-popup-blocking")
        options.add_argument("--disable-renderer-backgrounding")
        options.add_argument("--disable-backgrounding-occluded-windows")
        options.add_argument("--disable-features=TranslateUI,OptimizationHintsFetching")

    block_images = int(os.environ.get("BLOCK_IMAGES", "2"))
    block_css = int(os.environ.get("BLOCK_CSS", "2"))
    block_fonts = int(os.environ.get("BLOCK_FONTS", "2"))

    prefs = {
        "intl.accept_languages": browser_lang,
        "credentials_enable_service": False,
        "profile.password_manager_enabled": False,
        "profile.password_manager_leak_detection": False,
        "autofill.profile_enabled": False,
        "autofill.credit_card_enabled": False,
        "signin.allowed": False,
        "signin.allowed_on_next_startup": False,
        "browser.show_home_button": False,
        "browser.has_seen_welcome_page": True,
        "browser.check_default_browser": False,
        "distribution.import_bookmarks": False,
        "distribution.import_history": False,
        "distribution.import_search_engine": False,
        "distribution.import_saved_passwords": False,
        "distribution.skip_first_run_ui": True,
    }
    if block_images == 2:
        prefs["profile.managed_default_content_settings.images"] = 2
        options.add_argument('--blink-settings=imagesEnabled=false')
    if block_css == 2:
        prefs["profile.managed_default_content_settings.stylesheet"] = 2
    if block_fonts == 2:
        prefs["profile.managed_default_content_settings.fonts"] = 2

    options.add_experimental_option("prefs", prefs)

    proxy_dir = None
    if proxy and "@" in proxy:
        proxy_dir = create_proxy_extension_fn(proxy, cleanup_root)
        if proxy_dir:
            options.add_argument(f"--load-extension={proxy_dir}")
            options.add_argument(f"--disable-extensions-except={proxy_dir}")
    elif proxy:
        options.add_argument(f'--proxy-server={proxy}')
    else:
        system_proxy = resolve_env_proxy_server()
        if system_proxy:
            bypass_list = build_env_proxy_bypass_list()
            options.add_argument(f"--proxy-server={system_proxy}")
            options.add_argument(f"--proxy-bypass-list={bypass_list}")
            _debug_log_browser_system_native_proxy(
                startup_url=startup_url,
                system_proxy=system_proxy,
                bypass_list=bypass_list,
            )
        else:
            _debug_log_browser_system_native_proxy(
                startup_url=startup_url,
                system_proxy=None,
                bypass_list=build_env_proxy_bypass_list(),
            )

    if proxy:
        options.add_argument("--proxy-bypass-list=<-loopback>;localhost;127.0.0.1")

    options.add_argument('--log-level=3')
    options.add_argument('--disable-crash-reporter')
    if remove_args:
        filtered_args = []
        for arg in list(getattr(options, 'arguments', [])):
            base = arg.split('=', 1)[0]
            if arg in remove_args or base in remove_args:
                continue
            filtered_args.append(arg)
        options._arguments = filtered_args
    options.add_argument('--disable-in-process-stack-traces')
    options.page_load_strategy = 'eager'

    use_uc = (os.environ.get("USE_UNDETECTED_CHROMEDRIVER", "1") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
    )
    if resolved_backend == "camoufox":
        use_uc = (os.environ.get("CAMOUFOX_USE_UNDETECTED_CHROMEDRIVER", "0") or "0").strip().lower() not in (
            "0",
            "false",
            "no",
        )

    if browser_user_data_dir and not native_camoufox_bootstrapped:
        _cleanup_stale_browser_startup_state(browser_user_data_dir)

    chromedriver_binary = resolve_chromedriver_binary_path()
    driver = None
    if use_uc and uc is not None:
        try:
            with _uc_init_lock:
                options._arguments = _FilteredChromeArgumentList(  # type: ignore[attr-defined]
                    list(getattr(options, "arguments", [])),
                    blocked_bases={"--no-sandbox", "--test-type"},
                    dedupe_bases={
                        "--lang",
                        "--log-level",
                        "--no-default-browser-check",
                        "--no-first-run",
                        "--no-sandbox",
                        "--remote-debugging-host",
                        "--remote-debugging-port",
                        "--user-agent",
                        "--user-data-dir",
                        "--window-size",
                    },
                )
                uc_kwargs: dict[str, Any] = {"options": options}
                uc_kwargs["suppress_welcome"] = True
                uc_kwargs["use_subprocess"] = False
                uc_kwargs["no_sandbox"] = False
                if browser_binary:
                    uc_kwargs["browser_executable_path"] = browser_binary
                if chromedriver_binary:
                    uc_kwargs["driver_executable_path"] = chromedriver_binary
                if browser_user_data_dir:
                    uc_kwargs["user_data_dir"] = browser_user_data_dir
                vm = resolve_chrome_version_main_fn()
                if vm:
                    uc_kwargs["version_main"] = vm
                driver = uc.Chrome(**uc_kwargs)
        except Exception as e:
            _ = e
            driver = None

    if driver is None:
        service = Service(executable_path=chromedriver_binary) if chromedriver_binary else Service()
        driver = webdriver.Chrome(service=service, options=options)

    if headless == 0 and desired_window_size is not None:
        w, h = desired_window_size
        try:
            win = driver.execute_cdp_cmd("Browser.getWindowForTarget", {})
            win_id = int(win.get("windowId"))
            driver.execute_cdp_cmd("Browser.setWindowBounds", {
                "windowId": win_id,
                "bounds": {"windowState": "normal"}
            })
            driver.execute_cdp_cmd("Browser.setWindowBounds", {
                "windowId": win_id,
                "bounds": {"left": 0, "top": 0, "width": int(w), "height": int(h)}
            })
        except Exception:
            try:
                driver.set_window_rect(0, 0, w, h)
            except Exception:
                try:
                    driver.set_window_size(w, h)
                except Exception:
                    pass

    try:
        patch_driver_sourceurl(driver)
    except Exception:
        pass

    try:
        handles = list(driver.window_handles or [])
        if handles:
            primary = handles[0]
            for handle in handles[1:]:
                try:
                    driver.switch_to.window(handle)
                    driver.close()
                except Exception:
                    pass
            driver.switch_to.window(primary)
    except Exception:
        pass

    if startup_url:
        try:
            cur = str(getattr(driver, "current_url", "") or "")
        except Exception:
            cur = ""
        if startup_url not in cur:
            try:
                driver.get(startup_url)
            except Exception:
                pass

    apply_runtime_stealth_fn(driver, headless=headless)

    try:
        blocked_urls: list[str] = []
        if block_images == 2:
            blocked_urls.extend([
                "*.png",
                "*.jpg",
                "*.jpeg",
                "*.gif",
                "*.webp",
                "*.avif",
                "*.svg",
                "*.ico",
            ])
        if block_css == 2:
            blocked_urls.extend(["*.css"])
        if block_fonts == 2:
            blocked_urls.extend([
                "*.woff",
                "*.woff2",
                "*.ttf",
                "*.otf",
                "*.eot",
            ])
        if blocked_urls:
            driver.execute_cdp_cmd("Network.setBlockedURLs", {"urls": blocked_urls})
    except Exception:
        pass

    try:
        setattr(driver, "_neuro_browser_backend", resolved_backend)
    except Exception:
        pass
    try:
        setattr(driver, "_neuro_browser_user_data_dir", browser_user_data_dir or "")
        setattr(driver, "_neuro_browser_startup_url", startup_url or "")
        setattr(driver, "_neuro_browser_proxy", proxy or "")
    except Exception:
        pass
    try:
        setattr(driver, "_neuro_camoufox_native_metadata", native_camoufox_metadata)
    except Exception:
        pass

    return driver, (cleanup_root or proxy_dir)
