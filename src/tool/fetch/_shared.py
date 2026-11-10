"""Fetch 的编码、裁剪与内容整形纯函数。"""

from __future__ import annotations

import re
from typing import Dict, Tuple

from bs4 import BeautifulSoup
from markdownify import markdownify as md

# 单次抓取的最大响应体，防止 read 到超大文件把内存打满
MAX_BYTES = 2 * 1024 * 1024
# 正文提取时直接丢弃的标签（导航/页脚/脚本等，对阅读没有价值）
STRIP_TAGS = (
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

_CHARSET_RE = re.compile(r"charset=([\w-]+)", re.I)


def detect_charset(content_type: str | None, default: str = "utf-8") -> str:
    """从 Content-Type 提取 charset，缺失时返回 default。"""
    match = _CHARSET_RE.search(content_type or "")
    return match.group(1) if match else default


def decode_bytes(data: bytes, charset: str) -> str:
    """按声明编码解码，未知编码回落 UTF-8 并替换非法字节。"""
    try:
        return data.decode(charset, errors="replace")
    except LookupError:
        return data.decode("utf-8", errors="replace")


def clip_bytes(data: bytes, limit: int = MAX_BYTES) -> bytes:
    """按字节上限裁剪响应体。"""
    return data[:limit]


def looks_like_raw_text_url(url: str) -> bool:
    """判断地址是否直接返回纯文本/原始内容，无需 HTML 解析。"""
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
    return bool(
        re.search(
            r"\.(json|txt|md|py|js|ts|yaml|yml|toml|ini|cfg|csv|log|xml)(\?|$)", u
        )
    )


def html_to_markdown(html: str, url: str) -> Tuple[str, str]:
    """HTML → 正文 markdown：去噪、优先 main/article、正文过短时退化为全文本。"""
    soup = BeautifulSoup(html, "html.parser")
    doc_title = soup.title.string if soup.title and soup.title.string else url

    for tag in soup(STRIP_TAGS):
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

    return doc_title, markdown_text


def build_raw_text_result(
    url: str, text: str, content_type: str = ""
) -> Dict[str, str]:
    """把原始文本包装成 fetch 的统一返回结构。"""
    path = url.split("?", 1)[0].lower()
    fenced_lang = ""
    if path.endswith(".json"):
        fenced_lang = "json"
    elif path.endswith(".py"):
        fenced_lang = "python"
    elif path.endswith((".md", ".markdown")):
        # Markdown 直接原样返回（不加代码块）
        return {
            "url": url,
            "title": f"raw: {url.rsplit('/', 1)[-1].split('?', 1)[0] or url}",
            "content": text,
            "content_type": "markdown",
        }
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
    }
