"""
OpenAI ChatGPT 浏览器环境指纹配置

这些数据模拟真实浏览器环境，用于 PoW token 和 Sentinel token 生成。
基于 Chrome 131 / Windows 10 的浏览器指纹数据。
"""

from __future__ import annotations

# ============================================
# 基础配置
# ============================================

# CPU 核心数 - 用于 config 数组中的 core 值
CORES = [8, 12, 16, 24, 32]

# 屏幕分辨率组合 (width + height)
SCREENS = [
    3000,   # 1920+1080
    3200,   # 1920+1280
    3840,   # 2560+1280
    4000,   # 2560+1440
    4400,   # 2560+1840
    6000,   # 3840+2160
]

import logging
import os
import re
import time
from typing import Callable

from curl_cffi import requests as tls_requests

# 最大 PoW 迭代次数
MAX_ATTEMPTS = 500000

logger = logging.getLogger(__name__)

# chatgpt.com 部署标识 (data-build 属性)
# 现在默认动态获取，但允许调用方注入 HTML 获取逻辑，
# 这样运行时可以复用现有 session / proxy 栈，避免额外绕路。
DEFAULT_DATA_BUILD = "prod-f501fe933b3edf57aea882da888e1a544df99840"
_cached_data_build: str | None = None
_cached_data_build_expires_at: float | None = None


def _extract_data_build(html: str) -> str | None:
    match = re.search(r'data-build="([^"]+)"', html or "")
    if not match:
        return None
    value = str(match.group(1) or "").strip()
    return value or None


def invalidate_data_build_cache() -> None:
    global _cached_data_build, _cached_data_build_expires_at
    _cached_data_build = None
    _cached_data_build_expires_at = None


def get_data_build(fetch_html: Callable[[], str] | None = None) -> str:
    global _cached_data_build, _cached_data_build_expires_at

    cache_ttl_seconds = max(
        0,
        int(os.environ.get("OPENAI_DATA_BUILD_CACHE_TTL_SECONDS", "900") or "900"),
    )
    now = time.monotonic()
    if (
        _cached_data_build is not None
        and _cached_data_build_expires_at is not None
        and now < _cached_data_build_expires_at
    ):
        return _cached_data_build

    env_override = (os.environ.get("OPENAI_DATA_BUILD") or "").strip()
    if env_override:
        _cached_data_build = env_override
        _cached_data_build_expires_at = now + cache_ttl_seconds if cache_ttl_seconds > 0 else now
        return _cached_data_build

    try:
        logger.info("Fetching latest data-build from chatgpt.com...")
        if fetch_html is None:
            resp = tls_requests.get("https://chatgpt.com/", impersonate="chrome", timeout=10)
            resp.raise_for_status()
            html = resp.text
        else:
            html = fetch_html()

        data_build = _extract_data_build(html)
        if data_build:
            _cached_data_build = data_build
            _cached_data_build_expires_at = now + cache_ttl_seconds if cache_ttl_seconds > 0 else now
            logger.info(f"Successfully fetched dynamic data-build: {_cached_data_build}")
            return _cached_data_build
        logger.warning("Could not find data-build in HTML, falling back to default.")
    except Exception as e:
        logger.error(f"Failed to fetch data-build dynamically: {e}")

    # 如果抓取失败，退回默认值保证代码不报错退出
    _cached_data_build = DEFAULT_DATA_BUILD
    _cached_data_build_expires_at = now + cache_ttl_seconds if cache_ttl_seconds > 0 else now
    return _cached_data_build

# ============================================
# 默认浏览器 User-Agent
# ============================================
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# ============================================
# Navigator 对象的键值对指纹数据
# 随机从中选取一个，用于 config 数组
# ============================================
NAVIGATOR_KEYS = [
    "registerProtocolHandler−function registerProtocolHandler() { [native code] }",
    "storage−[object StorageManager]",
    "locks−[object LockManager]",
    "appCodeName−Mozilla",
    "permissions−[object Permissions]",
    "share−function share() { [native code] }",
    "webdriver−false",
    "managed−[object NavigatorManagedData]",
    "canShare−function canShare() { [native code] }",
    "vendor−Google Inc.",
    "mediaDevices−[object MediaDevices]",
    "vibrate−function vibrate() { [native code] }",
    "storageBuckets−[object StorageBucketManager]",
    "mediaCapabilities−[object MediaCapabilities]",
    "getGamepads−function getGamepads() { [native code] }",
    "bluetooth−[object Bluetooth]",
    "cookieEnabled−true",
    "virtualKeyboard−[object VirtualKeyboard]",
    "product−Gecko",
    "xr−[object XRSystem]",
    "clipboard−[object Clipboard]",
    "unregisterProtocolHandler−function unregisterProtocolHandler() { [native code] }",
    "productSub−20030107",
    "login−[object NavigatorLogin]",
    "vendorSub−",
    "getInstalledRelatedApps−function getInstalledRelatedApps() { [native code] }",
    "webkitGetUserMedia−function webkitGetUserMedia() { [native code] }",
    "appName−Netscape",
    "presentation−[object Presentation]",
    "onLine−true",
    "mimeTypes−[object MimeTypeArray]",
    "credentials−[object CredentialsContainer]",
    "serviceWorker−[object ServiceWorkerContainer]",
    "keyboard−[object Keyboard]",
    "gpu−[object GPU]",
    "webkitPersistentStorage−[object DeprecatedStorageQuota]",
    "doNotTrack",
    "clearAppBadge−function clearAppBadge() { [native code] }",
    "serial−[object Serial]",
    "requestMIDIAccess−function requestMIDIAccess() { [native code] }",
    "requestMediaKeySystemAccess−function requestMediaKeySystemAccess() { [native code] }",
    "pdfViewerEnabled−true",
    "language−en-US",
    "setAppBadge−function setAppBadge() { [native code] }",
    "geolocation−[object Geolocation]",
    "userAgentData−[object NavigatorUAData]",
    "getUserMedia−function getUserMedia() { [native code] }",
    "sendBeacon−function sendBeacon() { [native code] }",
    "hardwareConcurrency−16",
    "windowControlsOverlay−[object WindowControlsOverlay]",
    "scheduling−[object Scheduling]",
]

# ============================================
# Document 对象的 key（随机选取）
# ============================================
DOCUMENT_KEYS = [
    "_reactListeningcfilawjnerp",
    "_reactListening9ne2dfo1i47",
    "_reactListening410nzwhan2a",
    "_reactListeningo743lnnpvdg",
    "location",
]

# ============================================
# Window 对象的 key 列表（随机选取）
# 这些 key 代表 window 对象上可枚举的属性
# ============================================
WINDOW_KEYS = [
    "0", "window", "self", "document", "name", "location",
    "customElements", "history", "navigation", "locationbar",
    "menubar", "personalbar", "scrollbars", "statusbar", "toolbar",
    "status", "closed", "frames", "length", "top", "opener", "parent",
    "frameElement", "navigator", "origin", "external", "screen",
    "innerWidth", "innerHeight", "scrollX", "pageXOffset", "scrollY",
    "pageYOffset", "visualViewport", "screenX", "screenY", "outerWidth",
    "outerHeight", "devicePixelRatio", "clientInformation", "screenLeft",
    "screenTop", "styleMedia", "onsearch", "isSecureContext", "trustedTypes",
    "performance", "onappinstalled", "onbeforeinstallprompt", "crypto",
    "indexedDB", "sessionStorage", "localStorage",
    "onbeforexrselect", "onabort", "onbeforeinput", "onbeforematch",
    "onbeforetoggle", "onblur", "oncancel", "oncanplay", "oncanplaythrough",
    "onchange", "onclick", "onclose",
    "oncontentvisibilityautostatechange", "oncontextlost",
    "oncontextmenu", "oncontextrestored", "oncuechange", "ondblclick",
    "ondrag", "ondragend", "ondragenter", "ondragleave", "ondragover",
    "ondragstart", "ondrop", "ondurationchange", "onemptied", "onended",
    "onerror", "onfocus", "onformdata", "oninput", "oninvalid",
    "onkeydown", "onkeypress", "onkeyup", "onload", "onloadeddata",
    "onloadedmetadata", "onloadstart", "onmousedown", "onmouseenter",
    "onmouseleave", "onmousemove", "onmouseout", "onmouseover",
    "onmouseup", "onmousewheel", "onpause", "onplay", "onplaying",
    "onprogress", "onratechange", "onreset", "onresize", "onscroll",
    "onsecuritypolicyviolation", "onseeked", "onseeking", "onselect",
    "onslotchange", "onstalled", "onsubmit", "onsuspend", "ontimeupdate",
    "ontoggle", "onvolumechange", "onwaiting",
    "onwebkitanimationend", "onwebkitanimationiteration",
    "onwebkitanimationstart", "onwebkittransitionend", "onwheel",
    "onauxclick", "ongotpointercapture", "onlostpointercapture",
    "onpointerdown", "onpointermove", "onpointerrawupdate", "onpointerup",
    "onpointercancel", "onpointerover", "onpointerout", "onpointerenter",
    "onpointerleave", "onselectstart", "onselectionchange",
    "onanimationend", "onanimationiteration", "onanimationstart",
    "ontransitionrun", "ontransitionstart", "ontransitionend",
    "ontransitioncancel", "onafterprint", "onbeforeprint",
    "onbeforeunload", "onhashchange", "onlanguagechange", "onmessage",
    "onmessageerror", "onoffline", "ononline", "onpagehide", "onpageshow",
    "onpopstate", "onrejectionhandled", "onstorage",
    "onunhandledrejection", "onunload", "crossOriginIsolated",
    "scheduler", "alert", "atob", "blur", "btoa",
    "cancelAnimationFrame", "cancelIdleCallback", "captureEvents",
    "clearInterval", "clearTimeout", "close", "confirm",
    "createImageBitmap", "fetch", "find", "focus", "getComputedStyle",
    "getSelection", "matchMedia", "moveBy", "moveTo", "open",
    "postMessage", "print", "prompt", "queueMicrotask", "releaseEvents",
    "reportError", "requestAnimationFrame", "requestIdleCallback",
    "resizeBy", "resizeTo", "scroll", "scrollBy", "scrollTo",
    "setInterval", "setTimeout", "stop", "structuredClone",
    "webkitCancelAnimationFrame", "webkitRequestAnimationFrame",
    "chrome", "caches", "cookieStore",
    "ondevicemotion", "ondeviceorientation", "ondeviceorientationabsolute",
    "launchQueue", "documentPictureInPicture", "getScreenDetails",
    "queryLocalFonts", "showDirectoryPicker", "showOpenFilePicker",
    "showSaveFilePicker", "originAgentCluster", "onpageswap",
    "onpagereveal", "credentialless", "speechSynthesis", "onscrollend",
    "webkitRequestFileSystem", "webkitResolveLocalFileSystemURL",
    # ChatGPT/Next.js 特有全局变量
    "__remixContext", "__oai_SSR_TTI", "__remixManifest",
    "__reactRouterVersion", "DD_RUM", "__REACT_INTL_CONTEXT__",
    "filterCSS", "filterXSS", "__SEGMENT_INSPECTOR__", "DD_LOGS",
    "regeneratorRuntime", "_g", "__remixRouteModules", "__remixRouter",
    "__STATSIG_SDK__", "__STATSIG_JS_SDK__",
    "__STATSIG_RERENDER_OVERRIDE__", "_oaiHandleSessionExpired",
]

# ============================================
# API 端点
# ============================================
CHATGPT_BASE_URL = "https://chatgpt.com"
SENTINEL_CHAT_REQUIREMENTS_URL = f"{CHATGPT_BASE_URL}/backend-anon/sentinel/chat-requirements"
SENTINEL_REQ_URL = f"{CHATGPT_BASE_URL}/backend-api/sentinel/req"
CONVERSATION_URL = f"{CHATGPT_BASE_URL}/backend-anon/conversation"

# ============================================
# 默认 HTTP 请求头
# ============================================
DEFAULT_HEADERS = {
    "accept": "*/*",
    "accept-encoding": "gzip, deflate, br, zstd",
    "accept-language": "en-US,en;q=0.8",
    "content-type": "application/json",
    "origin": CHATGPT_BASE_URL,
    "referer": f"{CHATGPT_BASE_URL}/",
    "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "user-agent": DEFAULT_USER_AGENT,
}
