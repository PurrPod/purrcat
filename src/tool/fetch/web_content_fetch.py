import re
import urllib.error
import urllib.request
from typing import Dict, Optional, Tuple

from bs4 import BeautifulSoup
from markdownify import markdownify as md

# 单次抓取的最大响应体，防止 read 到超大文件把内存打满
_MAX_BYTES = 2 * 1024 * 1024
# 正文提取时直接丢弃的标签（导航/页脚/脚本等，对阅读没有价值）
_STRIP_TAGS = (
    "script",
    "style",
    "noscript",
    "iframe",
    "svg",
    "nav",
    "footer",
    "header",
    "aside",
)


def _looks_like_raw_text_url(url: str) -> bool:
    """
    判断 URL 是否属于「直接返回纯文本/原始内容」的场景。
    这类地址不需要走 HTML 解析，直接按文本读取并加代码块返回。
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
    """纯文本地址快速通道：直接下载原始内容，按 text/markdown 返回。"""
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
            data = resp.read(_MAX_BYTES + 1)
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
        return {
            "url": url,
            "title": f"raw: {url.rsplit('/', 1)[-1].split('?', 1)[0] or url}",
            "content": text,
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


def _html_to_markdown(html: str, url: str) -> Tuple[str, str]:
    """HTML → 正文 markdown：去噪、优先 main/article、正文过短时退化为全文本。"""
    soup = BeautifulSoup(html, "html.parser")
    doc_title = soup.title.string if soup.title and soup.title.string else url

    for tag in soup(_STRIP_TAGS):
        tag.decompose()

    main_content = soup.find("main") or soup.find("article")
    if not main_content:
        main_content = soup.find("body") or soup

    markdown_text = md(str(main_content), heading_style="ATX")
    markdown_text = re.sub(r"\n{3,}", "\n\n", markdown_text).strip()

    if len(markdown_text) < 150:
        paragraphs = soup.find_all(
            ["h1", "h2", "h3", "h4", "p", "li", "code", "div"]
        )
        text_lines = []
        for p in paragraphs:
            text = p.get_text(strip=True)
            if text and text not in text_lines:
                text_lines.append(text)
        markdown_text = "\n\n".join(text_lines)

    return doc_title, markdown_text


def _fetch_html_http(url: str, timeout: int = 20) -> Tuple[Optional[Dict], Optional[str]]:
    """curl_cffi（chrome 指纹）直接抓 HTML，再转 markdown。

    不做 JS 渲染：需要前端渲染的单页应用正文可能为空，此时给出明确提示，
    让 agent 改用浏览器工具（桌面端由 Electron 的 CDP 浏览器接管）。
    """
    from curl_cffi import requests

    try:
        resp = requests.get(
            url,
            impersonate="chrome",
            timeout=timeout,
            allow_redirects=True,
            headers={"Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"},
        )
    except Exception as e:
        return None, f"抓取失败: {e}"

    try:
        if resp.status_code >= 400:
            return None, f"HTTP {resp.status_code}: {url}"

        charset = "utf-8"
        content_type = resp.headers.get("Content-Type", "") or ""
        m = re.search(r"charset=([\w-]+)", content_type, re.I)
        if m:
            charset = m.group(1)

        try:
            html = resp.content[:_MAX_BYTES].decode(charset, errors="replace")
        except LookupError:
            html = resp.content[:_MAX_BYTES].decode("utf-8", errors="replace")
    finally:
        resp.close()

    doc_title, markdown_text = _html_to_markdown(html, url)

    if len(markdown_text) < 150:
        return None, (
            f"页面正文过短（{len(markdown_text)} 字符），可能是需要 JS 渲染的页面。"
            "HTTP 抓取不执行脚本，请改用浏览器工具打开该地址。"
        )

    return {
        "url": url,
        "title": doc_title,
        "content": markdown_text,
        "content_type": "html",
    }, None


def web_content_fetch(url: str) -> Tuple[Optional[Dict], Optional[str]]:
    """FETCH(source='web') 的同步入口：纯文本直读，HTML 走 HTTP 抓取 + 正文抽取。

    不依赖 Playwright / 无头浏览器，桌面安装包里也不会再带 chromium。
    """
    if _looks_like_raw_text_url(url):
        return _fast_fetch_raw_text(url, timeout=20)

    return _fetch_html_http(url)
