import asyncio
import re
import urllib.request
import urllib.error
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional, Tuple
from bs4 import BeautifulSoup
from markdownify import markdownify as md
from playwright.async_api import (
    async_playwright,
    TimeoutError as PlaywrightTimeoutError,
)


def _looks_like_raw_text_url(url: str) -> bool:
    """
    判断 URL 是否属于「直接返回纯文本/原始内容」的场景。
    这类地址用 Playwright 加载经常陷入无尽等待（networkidle 永远不触发、
    or 浏览器非 HTML 渲染挂起），所以提前绕开，直接走 HTTP 读取+截断。
    """
    u = (url or "").lower()
    raw_host_markers = [
        "raw.githubusercontent.com",
        "gist.githubusercontent.com",
        "cdn.jsdelivr.net",
        "unpkg.com",
        "pastebin.com/raw",
    ]
    if any(m in u for m in raw_host_markers):
        return True
    # 常见纯文本后缀
    if re.search(
        r"\.(json|txt|md|py|js|ts|yaml|yml|toml|ini|cfg|csv|log|xml)(\?|$)", u
    ):
        return True
    return False


def _fast_fetch_raw_text(
    url: str, timeout: int = 20
) -> Tuple[Optional[Dict], Optional[str]]:
    """
    纯文本地址快速通道：直接 urllib 下载，按 text/markdown 返回，
    不再启动 Playwright 浏览器（避免 FETCH 工具无限卡死）。
    """
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 purrcat-fetch-raw/1.0",
            "Accept": "*/*",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            content_type = resp.headers.get("Content-Type", "")
            # 限制最大 2MB 防止 OOM
            data = resp.read(2 * 1024 * 1024 + 1)
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}: {e.reason}"
    except (urllib.error.URLError, TimeoutError) as e:
        return None, f"下载失败: {e}"

    try:
        text = data.decode(charset, errors="replace")
    except LookupError:
        text = data.decode("utf-8", errors="replace")

    # URL 推断内容类型
    path = url.split("?", 1)[0].lower()
    fenced_lang = ""
    if path.endswith(".json"):
        fenced_lang = "json"
    elif path.endswith(".py"):
        fenced_lang = "python"
    elif path.endswith(".md") or path.endswith(".markdown"):
        # Markdown 直接原样返回（不加代码块）
        content = text
        return {
            "url": url,
            "title": f"raw: {url.rsplit('/', 1)[-1].split('?', 1)[0] or url}",
            "content": content,
            "content_type": "markdown",
        }, None
    elif path.endswith((".js", ".ts", ".tsx", ".jsx")):
        fenced_lang = "javascript"
    elif path.endswith((".yaml", ".yml")):
        fenced_lang = "yaml"
    elif path.endswith((".toml", ".ini", ".cfg")):
        fenced_lang = "ini"
    elif path.endswith(".csv"):
        fenced_lang = "csv"
    elif path.endswith(".xml"):
        fenced_lang = "xml"

    content = (
        f"```\n{text}\n```" if not fenced_lang else f"```{fenced_lang}\n{text}\n```"
    )

    filename = url.rsplit("/", 1)[-1].split("?", 1)[0] or "raw"
    return {
        "url": url,
        "title": f"raw: {filename} ({content_type.split(';', 1)[0] or 'text'})",
        "content": content,
        "content_type": "text",
    }, None


async def web_content_fetch_playwright(
    url: str, timeout_ms: int = 30000
) -> Tuple[Optional[Dict], Optional[str]]:
    # 🌟 先尝试快速通道：纯文本地址不启浏览器
    if _looks_like_raw_text_url(url):
        return _fast_fetch_raw_text(url, timeout=max(5, timeout_ms // 1000))

    try:
        async with async_timeout(timeout_ms + 10000), async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
                )
                page = await context.new_page()

                try:
                    await page.goto(url, wait_until="networkidle", timeout=timeout_ms)
                except PlaywrightTimeoutError:
                    # 超时但仍尝试读取已加载的内容
                    pass

                # ----------------------------------------------------------------
                # 1. 反爬拦截识别
                # ----------------------------------------------------------------
                is_blocked = await page.evaluate(r"""() => {
                    const selectors = ['.cf-turnstile', '[name="cf-turnstile-response"]', 'iframe[src*="challenges.cloudflare.com"]', '#challenge-running', '#cf-challenge-running'];
                    const text = document.body ? document.body.innerText.toLowerCase() : "";
                    return selectors.some(s => document.querySelector(s) !== null) || text.includes("verify you are human");
                }""")

                if is_blocked:
                    await browser.close()
                    return {
                        "url": url,
                        "title": "Blocked by Anti-bot",
                        "content": f"# 访问受限\n\n**URL:** {url}\n\n⚠️ 网页被反爬机制拦截，无法自动获取。请尝试其他工具。",
                        "content_type": "error",
                    }, None

                # ----------------------------------------------------------------
                # 2. 平滑滚动（加总超时保护，避免无穷页面）
                # ----------------------------------------------------------------
                try:
                    await asyncio.wait_for(
                        page.evaluate(r"""
                            async () => {
                                await new Promise((resolve) => {
                                    let totalHeight = 0;
                                    let distance = 1000;
                                    let attempts = 0;
                                    const MAX_ATTEMPTS = 20;
                                    let timer = setInterval(() => {
                                        let scrollHeight = document.body.scrollHeight;
                                        window.scrollBy(0, distance);
                                        totalHeight += distance;
                                        attempts += 1;
                                        if(totalHeight >= scrollHeight - window.innerHeight || attempts >= MAX_ATTEMPTS){
                                            clearInterval(timer);
                                            resolve();
                                        }
                                    }, 200);
                                });
                            }
                        """),
                        timeout=10.0,
                    )
                except (asyncio.TimeoutError, PlaywrightTimeoutError):
                    pass

                try:
                    await page.wait_for_timeout(500)
                except Exception:
                    pass

                # ----------------------------------------------------------------
                # 3. 拍平 Shadow DOM
                # ----------------------------------------------------------------
                snapshot_data = await page.evaluate(r"""() => {
                    const baseUrl = document.baseURI || location.href;
                    const htmlClone = document.documentElement.cloneNode(true);
                    
                    function materializeShadowDom(sourceRoot, cloneRoot) {
                        const sourceElements = Array.from(sourceRoot.querySelectorAll("*"));
                        const cloneElements = Array.from(cloneRoot.querySelectorAll("*"));
                        for (let index = sourceElements.length - 1; index >= 0; index -= 1) {
                            const sourceElement = sourceElements[index];
                            const cloneElement = cloneElements[index];
                            const shadowRoot = sourceElement && sourceElement.shadowRoot;
                            if (!shadowRoot || !cloneElement || !shadowRoot.innerHTML) {
                                continue;
                            }
                            if (cloneElement.tagName && cloneElement.tagName.includes("-")) {
                                const wrapper = document.createElement("div");
                                wrapper.setAttribute("data-shadow-host", cloneElement.tagName.toLowerCase());
                                wrapper.innerHTML = shadowRoot.innerHTML;
                                cloneElement.replaceWith(wrapper);
                            } else {
                                cloneElement.innerHTML = shadowRoot.innerHTML;
                            }
                        }
                    }
                    
                    function toAbsolute(url) {
                        if (!url) return url;
                        try { return new URL(url, baseUrl).href; } catch { return url; }
                    }
                    
                    function absolutizeAttribute(root, selector, attribute) {
                        root.querySelectorAll(selector).forEach((element) => {
                            const value = element.getAttribute(attribute);
                            if (!value) return;
                            const absolute = toAbsolute(value);
                            if (absolute) element.setAttribute(attribute, absolute);
                        });
                    }

                    materializeShadowDom(document.documentElement, htmlClone);
                    
                    htmlClone.querySelectorAll("img[data-src], video[data-src], source[data-src]")
                        .forEach((element) => {
                            const dataSource = element.getAttribute("data-src");
                            const current = element.getAttribute("src");
                            if (dataSource && (!current || current === "" || current.startsWith("data:"))) {
                                element.setAttribute("src", dataSource);
                            }
                        });
                        
                    absolutizeAttribute(htmlClone, "a[href]", "href");
                    absolutizeAttribute(htmlClone, "img[src], video[src], source[src]", "src");
                    
                    return {
                        html: "<!doctype html>\n" + htmlClone.outerHTML,
                        finalUrl: location.href
                    };
                }""")

                html_content = snapshot_data["html"]
                final_url = snapshot_data["finalUrl"]
            finally:
                try:
                    await browser.close()
                except Exception:
                    pass
    except (asyncio.TimeoutError, TimeoutError):
        # 兜底：仍然用 HTTP 直读，避免用户永远等不到结果
        try:
            return _fast_fetch_raw_text(url, timeout=15)
        except Exception as e2:
            return None, f"Playwright 抓取超时且直读也失败: {e2}"
    except Exception as e:
        return None, f"Playwright 抓取失败: {e}"

    # ----------------------------------------------------------------
    # 4. 智能解析与清洗
    # ----------------------------------------------------------------
    soup = BeautifulSoup(html_content, "html.parser")
    doc_title = soup.title.string if soup.title else final_url

    for tag in soup(
        [
            "script",
            "style",
            "noscript",
            "iframe",
            "svg",
            "nav",
            "footer",
            "header",
            "aside",
        ]
    ):
        tag.decompose()

    main_content = soup.find("main") or soup.find("article")
    if not main_content:
        main_content = soup.find("body") or soup

    markdown_text = md(str(main_content), heading_style="ATX")
    markdown_text = re.sub(r"\n{3,}", "\n\n", markdown_text).strip()

    if len(markdown_text) < 150:
        paragraphs = soup.find_all(["h1", "h2", "h3", "h4", "p", "li", "code", "div"])
        text_lines = []
        for p in paragraphs:
            text = p.get_text(strip=True)
            if text and text not in text_lines:
                text_lines.append(text)
        markdown_text = "\n\n".join(text_lines)

    return {
        "url": url,
        "title": doc_title,
        "content": markdown_text,
        "content_type": "html",
    }, None


_SEC_HIGH_THRESHOLD = 600  # 大于 600 认为是毫秒单位


def _to_seconds(value: float) -> float:
    return value / 1000.0 if value > _SEC_HIGH_THRESHOLD else value


@asynccontextmanager
async def async_timeout(seconds: float):
    """
    统一的异步超时上下文管理器。

    - 优先使用 Python 3.11+ 的 ``asyncio.timeout``
    - 在 Python 3.10 上通过 ``asyncio.wait_for`` + Task 的等价实现兜底
    - 入参兼容「秒」或「毫秒」：> 600 视为毫秒
    """
    sec = _to_seconds(seconds)

    # 3.11+ 原生 asyncio.timeout
    native = getattr(asyncio, "timeout", None)
    if callable(native):
        try:
            async with native(sec):  # type: ignore[operator]
                yield
            return
        except asyncio.TimeoutError:
            raise

    # Python 3.10 回退：用 Task + wait_for 模拟
    async with _async_timeout_polyfill(sec):
        yield


@asynccontextmanager
async def _async_timeout_polyfill(sec: float):
    """Python 3.10 版 async_timeout：把 yield 块塞进一个临时 Task 并用 wait_for 定时"""
    # 实现参考：把 with 块包装为 async generator 的「挂起点」等待，通过 Future 完成通知
    entered = asyncio.Future()
    done = asyncio.Future()

    async def _wrap_body():
        entered.set_result(None)
        # 等待 with 块执行完毕（外部任务会 set_result）
        await done
        return None

    wrapper_task: Optional[asyncio.Task] = None
    timed_out = False
    try:
        wrapper_task = asyncio.create_task(asyncio.wait_for(_wrap_body(), timeout=sec))
        await entered  # 等待 wrapper 进入 yield 点
        yield
        done.set_result(None)  # 告诉 wrapper 执行完成
        await wrapper_task
    except asyncio.TimeoutError:
        timed_out = True
        raise
    finally:
        if not done.done():
            done.set_result(None)
        if wrapper_task is not None and not wrapper_task.done():
            if timed_out:
                # wait_for 超时会自动取消内层任务，但再保险一下
                wrapper_task.cancel()
            try:
                await wrapper_task
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass


def web_content_fetch(url: str) -> Tuple[Optional[Dict], Optional[str]]:
    """
    提供给原系统的同步接口入口。

    🌟 关键修复：对 raw.githubusercontent.com 等纯文本 URL 直接走
    urllib 快速通道，不启动 Playwright，彻底避免 FETCH(source='web', url=...)
    调用被 Playwright 无限卡死的问题。
    """
    # 快速通道（即使在同步阶段也先判断）
    if _looks_like_raw_text_url(url):
        return _fast_fetch_raw_text(url, timeout=20)

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    # 同步层再加一道总超时，防止 Playwright 进程/管道泄漏导致永久挂起
    import threading

    holder: Dict[str, Any] = {}

    def _runner():
        try:
            res = loop.run_until_complete(web_content_fetch_playwright(url))
            holder["result"] = res
        except BaseException as e:  # noqa: BLE001
            holder["error"] = e

    t = threading.Thread(target=_runner, daemon=True)
    t.start()
    t.join(timeout=70)  # 最多等待 70 秒，超过就放弃 Playwright 直读
    if "result" in holder:
        return holder["result"]
    if "error" in holder:
        return None, f"Playwright 抓取失败: {holder['error']}"

    # 70 秒仍未返回：降级为直读（Playwright 子进程不回收也不再阻塞用户）
    try:
        return _fast_fetch_raw_text(url, timeout=15)
    except Exception as e:
        return None, f"抓取超时（Playwright 无响应）且直读失败: {e}"
