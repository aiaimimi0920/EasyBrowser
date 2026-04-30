from __future__ import annotations

import dataclasses


@dataclasses.dataclass
class ChromeProviderConfig:
    headless: bool = True
    browser_binary: str = ""
    user_data_dir: str = ""
    use_undetected_chromedriver: bool = True
    stealth_mask_linux: bool = True


@dataclasses.dataclass
class CamoufoxProviderConfig:
    headless: bool = True
    os_name: str = "windows"
    ws_timeout_ms: int = 60000
    connect_timeout_ms: int = 20000


@dataclasses.dataclass
class GeekezProviderConfig:
    api_base_url: str = "http://127.0.0.1:52000"
    ensure_remote_debugging: bool = True
    auto_create_profile: bool = True


@dataclasses.dataclass
class BrowserbaseProviderConfig:
    api_key: str = ""
    project_id: str = ""
    base_url: str = "https://api.browserbase.com"
    default_region: str = ""
    keep_alive: bool = False


@dataclasses.dataclass
class EasyBrowserConfig:
    default_provider: str = "chrome"
    chrome: ChromeProviderConfig = dataclasses.field(default_factory=ChromeProviderConfig)
    camoufox: CamoufoxProviderConfig = dataclasses.field(default_factory=CamoufoxProviderConfig)
    geekez: GeekezProviderConfig = dataclasses.field(default_factory=GeekezProviderConfig)
    browserbase: BrowserbaseProviderConfig = dataclasses.field(default_factory=BrowserbaseProviderConfig)
