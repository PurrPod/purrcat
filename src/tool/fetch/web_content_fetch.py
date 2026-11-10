import json
import os
import urllib.error
import urllib.request
from typing import Dict, Optional, Tuple

from ._shared import (
    MAX_BYTES,
    build_raw_text_result,
    clip_bytes,
    decode_bytes,
    detect_charset,
    html_to_markdown,
    looks_like_raw_text_url,
)


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
            data = resp.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}: {e.reason}"
    except (urllib.error.URLError, TimeoutError) as e:
        return None, f"下载失败: {e}"

    text = decode_bytes(data, charset)
    return build_raw_text_result(url, text, content_type), None


def _fetch_html_http(
    url: str, timeout: int = 20
) -> Tuple[Optional[Dict], Optional[str]]:
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

        content_type = resp.headers.get("Content-Type", "") or ""
        charset = detect_charset(content_type)
        html = decode_bytes(clip_bytes(resp.content), charset)
    finally:
        resp.close()

    doc_title, markdown_text = html_to_markdown(html, url)

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


_CONTROL_STATE_FILE = os.path.join(
    os.path.expanduser("~"), ".purrcat", "run", "control.json"
)


def _render_via_host(url: str, timeout: int = 20) -> Optional[str]:
    """请桌面端宿主（Electron）用隐藏窗口渲染页面，返回渲染后的完整 HTML。

    宿主在 ~/.purrcat/run/control.json 暴露随机端口 + 令牌的控制口；
    纯服务端 / 容器里没有 Electron，读不到状态文件就直接返回 None。
    """
    try:
        with open(_CONTROL_STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
        port = int(state.get("port") or 0)
        token = str(state.get("token") or "")
        if not port or not token:
            return None
    except Exception:
        return None

    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/control/browser/render",
            data=json.dumps({"url": url, "timeout_ms": timeout * 1000}).encode("utf-8"),
            headers={
                "content-type": "application/json",
                "x-purrcat-token": token,
            },
            method="POST",
        )
        # 宿主侧有渲染超时，这里再多留一点网络往返余量
        with urllib.request.urlopen(req, timeout=timeout + 10) as resp:
            payload = json.load(resp)
        if payload.get("ok") and payload.get("html"):
            return payload["html"]
    except Exception as e:
        print(f"[Fetch] 宿主渲染失败: {e}")
    return None


def web_content_fetch(url: str) -> Tuple[Optional[Dict], Optional[str]]:
    """FETCH(source='web') 的同步入口。

    1. 纯文本地址（.md/.txt/.json 等）→ urllib 直读，不渲染
    2. 普通网页 → 优先让桌面端 Electron 渲染后取 DOM（懒加载、评论区等
       JS 内容也能拿到），HTTP 直抓只作为兜底
    3. 无宿主（服务端/容器）或渲染失败 → curl_cffi 抓原始 HTML + 正文抽取
    """
    if looks_like_raw_text_url(url):
        return _fast_fetch_raw_text(url, timeout=20)

    html = _render_via_host(url)
    if html:
        doc_title, markdown_text = html_to_markdown(html, url)
        if len(markdown_text) >= 150:
            return {
                "url": url,
                "title": doc_title,
                "content": markdown_text,
                "content_type": "html",
            }, None

    result, error = _fetch_html_http(url)
    if result is not None:
        return result, None
    if html:
        return None, "浏览器渲染后正文仍为空，页面可能需要登录或交互后才能显示内容。"
    return None, error
