# EasyBrowser 统一浏览器接口使用文档

## 概述

`easybrowser` 是一个 Python 包，为 4 个浏览器后端（Chrome、Camoufox、GeekezBrowser、Browserbase）提供统一的 Playwright 风格接口。

上层业务代码面向统一接口编写，底层自动分发到不同浏览器执行。

### 两层接口

| 层级 | 用途 | 入口 |
|------|------|------|
| **Layer 1** | Playwright 风格原子操作（goto, click, fill, evaluate 等） | `create_browser()` → `provider.launch()` → `ctx.new_page()` |
| **Layer 2** | 高级任务接口（一个调用完成整个业务流程） | `DefaultTaskExecutor.execute_task(TaskConfig)` |

### 支持的 Provider

| Provider | 引擎 | 连接方式 | 特点 |
|----------|------|----------|------|
| `chrome` | Selenium WebDriver | 本地进程 | 自研 stealth、undetected-chromedriver |
| `camoufox` | Playwright + Firefox | WebSocket | 反检测浏览器、OS 模拟 |
| `geekez` | Playwright + CDP | REST API + 远程调试 | Xray 代理、深度指纹隔离 |
| `browserbase` | Playwright + CDP | REST API + WebSocket | 云端浏览器 |

---

## 安装依赖

```bash
# 必需（所有 provider）
pip install selenium undetected-chromedriver playwright aiohttp

# Camoufox 专用
pip install camoufox

# 安装 Playwright 浏览器
python -m playwright install
```

---

## Layer 1: 低级浏览器操作

### 基本用法

```python
import asyncio
from easybrowser.factory import create_browser
from easybrowser.models import LaunchOptions, ProxyConfig, FingerprintConfig

async def main():
    # 1. 创建 provider
    provider = create_browser("chrome")

    # 2. 启动浏览器，获取 context
    ctx = await provider.launch(LaunchOptions(headless=True))

    # 3. 创建页面
    page = await ctx.new_page()

    # 4. 操作页面（与 Playwright 接口一致）
    await page.goto("https://example.com")
    print(f"标题: {await page.title()}")
    print(f"URL: {page.url}")

    # 5. 清理
    await page.close()
    await ctx.close()
    await provider.close()

asyncio.run(main())
```

### 切换 Provider

只需改一个参数，其余代码完全不变：

```python
# Chrome
provider = create_browser("chrome")

# Camoufox
provider = create_browser("camoufox")

# GeekezBrowser（需先启动桌面应用）
provider = create_browser("geekez", api_base_url="http://127.0.0.1:52000")

# Browserbase（需设置 API Key）
provider = create_browser("browserbase", api_key="xxx", project_id="xxx")
```

### LaunchOptions — 启动配置

```python
from easybrowser.models import LaunchOptions, ProxyConfig, FingerprintConfig

options = LaunchOptions(
    headless=True,                    # 无头模式
    proxy=ProxyConfig(                # 代理配置
        server="http://proxy:8080",
        username="user",
        password="pass",
    ),
    fingerprint=FingerprintConfig(    # 指纹配置
        user_agent="Mozilla/5.0 ...",
        locale="en-US",
        timezone="America/New_York",
        screen_width=1920,
        screen_height=1080,
        webgl_vendor="Intel Inc.",
        webgl_renderer="Intel Iris OpenGL Engine",
        hardware_concurrency=8,
    ),
    user_data_dir="/path/to/profile", # 用户数据目录
    extra={                           # Provider 专属参数
        "os_name": "windows",         # Camoufox: OS 模拟
        "profile_name": "my-env",     # GeekezBrowser: profile 名
        "project_id": "xxx",          # Browserbase: 项目 ID
    },
)

ctx = await provider.launch(options)
```

### BrowserPage — 页面操作 API

#### 导航

```python
from easybrowser.models import NavigationOptions

# 跳转
await page.goto("https://example.com")
await page.goto("https://example.com", options=NavigationOptions(
    wait_until="networkidle",
    timeout_ms=60000,
))

# 刷新 / 前进 / 后退
await page.reload()
await page.go_back()
await page.go_forward()
```

#### 元素交互

```python
# 点击
await page.click("button.submit")

# 双击
await page.dblclick("div.editable")

# 鼠标悬停
await page.hover("nav .dropdown-trigger")

# 触摸点击（移动端模拟）
await page.tap("button.mobile-action")

# 聚焦元素
await page.focus("input[name='email']")

# 拖放
await page.drag_and_drop("div.draggable", "div.drop-zone")

# 填充（清空后输入）
await page.fill("input[name='email']", "user@example.com")

# 逐字符打字（模拟人类输入）
await page.type("input[name='password']", "secret123", delay_ms=100)

# 按键
await page.press("input[name='search']", "Enter")

# 下拉选择
await page.select_option("select#country", "US")

# 复选框
await page.check("input#agree")
await page.uncheck("input#newsletter")
```

#### 等待

```python
from easybrowser.models import WaitForSelectorOptions

# 等待元素出现
await page.wait_for_selector(".result-list")

# 等待元素消失
await page.wait_for_selector(".loading", options=WaitForSelectorOptions(
    state="hidden",
    timeout_ms=10000,
))

# 等待 URL 变化
await page.wait_for_url("dashboard")

# 等待页面加载完成
await page.wait_for_load_state("networkidle")

# 等待 JS 条件满足
await page.wait_for_function("document.querySelectorAll('.item').length > 5")

# 固定等待
await page.wait_for_timeout(2000)  # 2 秒
```

#### 读取内容

```python
# 获取页面源码
html = await page.content()

# 获取标题
title = await page.title()

# 当前 URL（同步属性）
current_url = page.url

# 元素文本
text = await page.inner_text("h1.title")

# 元素 HTML
html = await page.inner_html("div.content")

# 元素属性
href = await page.get_attribute("a.link", "href")

# 输入框的值
value = await page.input_value("input[name='email']")

# 元素是否可见
visible = await page.is_visible("div.error")
```

#### JavaScript 执行

```python
# 执行 JS 表达式
result = await page.evaluate("document.title")

# 带参数
result = await page.evaluate("(a, b) => a + b", 1, 2)

# 复杂操作
await page.evaluate("""
    () => {
        window.scrollTo(0, document.body.scrollHeight);
    }
""")
```

#### 截图与 PDF

```python
from easybrowser.models import ScreenshotOptions

# 获取截图 bytes
png_data = await page.screenshot()

# 保存到文件 + 全页截图
await page.screenshot(options=ScreenshotOptions(
    path="screenshot.png",
    full_page=True,
))

# JPEG 格式 + 质量
await page.screenshot(options=ScreenshotOptions(
    format="jpeg",
    quality=80,
))

# 导出 PDF（仅 Chromium headless 支持）
pdf_data = await page.pdf(path="page.pdf", format="A4")
```

#### 查询元素

```python
# 查找单个元素（返回 None 如果不存在）
el = await page.query_selector("div.result")

# 查找所有匹配元素
elements = await page.query_selector_all("li.item")
```

#### 页面配置

```python
# 设置视口大小
await page.set_viewport_size(1920, 1080)

# 设置额外 HTTP 头
await page.set_extra_http_headers({"X-Custom": "value"})

# 设置页面 HTML 内容
await page.set_content("<h1>Hello</h1><p>World</p>")
```

#### 注入 Script / Style

```python
# 注入外部脚本
await page.add_script_tag(url="https://cdn.example.com/lib.js")

# 注入内联脚本
await page.add_script_tag(content="window.myVar = 42;")

# 注入外部样式
await page.add_style_tag(url="https://cdn.example.com/theme.css")

# 注入内联样式
await page.add_style_tag(content="body { background: #f0f0f0; }")
```

#### iframe 操作

```python
# 获取所有 frame
all_frames = await page.frames()

# 按名称查找 frame
login_frame = await page.frame(name="login-iframe")

# 按 URL 查找 frame
ad_frame = await page.frame(url="ads.example.com")
```

#### 网络拦截（route）

```python
# 拦截图片请求（Playwright 后端原生支持）
async def block_images(route):
    await route.abort()

await page.route("**/*.{png,jpg,jpeg,gif}", block_images)

# 取消拦截
await page.unroute("**/*.{png,jpg,jpeg,gif}")
```

> 注意：Chrome (Selenium) 后端不支持 route/unroute，调用不会报错但无效果。
> 如需在 Chrome 后端拦截网络，请使用 `page.unwrap()` 获取原生 driver 后通过 CDP 操作。

### BrowserContext — 上下文管理

```python
# Cookie 操作
cookies = await ctx.cookies()
await ctx.add_cookies([{
    "name": "session",
    "value": "abc123",
    "domain": "example.com",
    "path": "/",
}])
await ctx.clear_cookies()

# 存储状态（包含 cookies + localStorage）
state = await ctx.storage_state()

# 注入初始化脚本（每个新页面自动执行）
await ctx.add_init_script("window.__test = true;")

# 获取所有页面
pages = await ctx.pages()

# 创建新页面
page2 = await ctx.new_page()

# 设置默认超时
await ctx.set_default_timeout(10000)
await ctx.set_default_navigation_timeout(60000)

# 权限管理
await ctx.grant_permissions(["geolocation", "notifications"])
await ctx.clear_permissions()

# 地理位置模拟
await ctx.set_geolocation({"latitude": 40.7128, "longitude": -74.0060})
await ctx.set_geolocation(None)  # 清除

# 离线模式
await ctx.set_offline(True)
await ctx.set_offline(False)

# 上下文级网络拦截
await ctx.route("**/api/**", handler_fn)
await ctx.unroute("**/api/**")
```

### unwrap() — 访问原生对象

当统一接口无法满足需求时，可以获取底层原生对象：

```python
# Chrome: 返回 Selenium WebDriver
driver = page.unwrap()
driver.execute_cdp_cmd("Network.enable", {})

# Camoufox/GeekezBrowser/Browserbase: 返回 Playwright Page
pw_page = page.unwrap()
await pw_page.route("**/*.png", lambda route: route.abort())
```

---

## Layer 2: 高级任务接口

### 基本用法

```python
import asyncio
from easybrowser.tasks import DefaultTaskExecutor
from easybrowser.tasks.handlers import NavigateHandler
from easybrowser.models import TaskConfig

async def main():
    # 1. 创建执行器
    executor = DefaultTaskExecutor()

    # 2. 注册任务处理器
    executor.register_handler("navigate", NavigateHandler())

    # 3. 执行任务（自动管理 provider/context/page 生命周期）
    result = await executor.execute_task(TaskConfig(
        task_type="navigate",
        provider="chrome",          # 可选，默认 "chrome"
        proxy="http://proxy:8080",  # 可选
        params={
            "url": "https://example.com",
            "screenshot": True,
        },
    ))

    print(f"成功: {result.success}")
    print(f"数据: {result.data}")       # {"title": "...", "url": "...", "screenshot_size": 12345}
    print(f"耗时: {result.duration_ms}ms")

asyncio.run(main())
```

### 自定义 TaskHandler

```python
from easybrowser.tasks.handler import TaskHandler
from easybrowser.interfaces.page import BrowserPage
from easybrowser.models import TaskConfig, TaskResult

class LoginHandler(TaskHandler):
    async def run(self, page: BrowserPage, config: TaskConfig) -> TaskResult:
        url = config.params["url"]
        username = config.params["username"]
        password = config.params["password"]

        await page.goto(url)
        await page.fill("input[name='username']", username)
        await page.fill("input[name='password']", password)
        await page.click("button[type='submit']")
        await page.wait_for_url("dashboard", timeout_ms=10000)

        title = await page.title()
        return TaskResult(
            success=True,
            task_type=config.task_type,
            provider=config.provider or "",
            data={"title": title, "url": page.url},
        )

# 注册并使用
executor.register_handler("login", LoginHandler())
result = await executor.execute_task(TaskConfig(
    task_type="login",
    provider="chrome",
    params={
        "url": "https://app.example.com/login",
        "username": "user@example.com",
        "password": "secret",
    },
))
```

### TaskConfig 参数

```python
from easybrowser.models import TaskConfig, FingerprintConfig

config = TaskConfig(
    task_type="login",                     # 任务类型（必须匹配已注册的 handler）
    provider="camoufox",                   # 使用哪个浏览器（可选，默认 chrome）
    proxy="http://user:pass@proxy:8080",   # 代理（可选）
    fingerprint=FingerprintConfig(         # 指纹（可选）
        user_agent="...",
        timezone="Asia/Shanghai",
    ),
    params={                               # 传给 handler 的业务参数
        "url": "https://example.com",
    },
    timeout_ms=120000,                     # 超时（毫秒）
)
```

### TaskResult 返回值

```python
@dataclass
class TaskResult:
    success: bool              # 是否成功
    task_type: str             # 任务类型
    provider: str              # 使用的 provider
    data: dict[str, Any]       # 业务数据
    error: str | None          # 错误信息（失败时）
    duration_ms: int           # 执行耗时（毫秒）
```

---

## Provider 专项说明

### Chrome

直接可用，无需额外配置。使用 `repos/chrome/` 的 `create_anonymous_driver()` 启动，自带 stealth 注入。

```python
provider = create_browser("chrome")
ctx = await provider.launch(LaunchOptions(headless=True))
```

### Camoufox

需安装 `camoufox` 包。启动时会自动拉起 camoufox server 子进程。

```python
provider = create_browser("camoufox")
ctx = await provider.launch(LaunchOptions(
    headless=True,
    extra={"os_name": "windows"},  # 模拟的操作系统
))
```

### GeekezBrowser

前提条件：
1. GeekezBrowser 桌面应用已启动
2. Settings 中 `enableRemoteDebugging` 已开启
3. API Server 已启动（默认端口 52000）

```python
provider = create_browser("geekez", api_base_url="http://127.0.0.1:52000")
ctx = await provider.launch(LaunchOptions(
    proxy=ProxyConfig(server="socks5://proxy:1080"),
    fingerprint=FingerprintConfig(
        timezone="America/New_York",
        locale="en-US",
    ),
    extra={"profile_name": "my-work-env"},  # 复用已有 profile
))
```

### Browserbase

需设置环境变量或构造时传参：

```bash
export BROWSERBASE_API_KEY="your-api-key"
export BROWSERBASE_PROJECT_ID="your-project-id"
```

```python
provider = create_browser("browserbase")
# 或显式传参
provider = create_browser("browserbase",
    api_key="your-api-key",
    project_id="your-project-id",
)
ctx = await provider.launch()
```

---

## 错误处理

所有错误继承自 `EasyBrowserError`：

```python
from easybrowser.models.errors import (
    EasyBrowserError,      # 基类
    NavigationError,       # 导航失败
    ElementNotFoundError,  # 元素未找到
    TimeoutError,          # 超时
    ConnectionError,       # 连接失败
    ProviderNotFoundError, # Provider 不存在
)

try:
    await page.goto("https://example.com")
    await page.click("button.submit", timeout_ms=5000)
except TimeoutError as e:
    print(f"超时: {e}")
    print(f"可重试: {e.retriable}")
except EasyBrowserError as e:
    print(f"错误类别: {e.category}")
    print(f"错误码: {e.code}")
```

---

## 查看可用 Provider

```python
from easybrowser.factory import available_providers

print(available_providers())
# ['browserbase', 'camoufox', 'chrome', 'geekez']
```

---

## 完整示例：多 Provider 对比

```python
import asyncio
from easybrowser.factory import create_browser
from easybrowser.models import LaunchOptions

async def test_provider(name: str):
    print(f"\n--- {name} ---")
    provider = create_browser(name)
    try:
        ctx = await provider.launch(LaunchOptions(headless=True))
        page = await ctx.new_page()
        await page.goto("https://example.com")
        print(f"  标题: {await page.title()}")
        print(f"  URL:  {page.url}")
        ss = await page.screenshot()
        print(f"  截图: {len(ss)} bytes")
        await page.close()
        await ctx.close()
    finally:
        await provider.close()

async def main():
    for name in ["chrome", "camoufox"]:
        await test_provider(name)

asyncio.run(main())
```
