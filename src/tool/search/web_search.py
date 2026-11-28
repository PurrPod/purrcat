"""Web 搜索模块 - 直接抓取 Bing 结果页（与 Fetch 完全解耦）

之所以不再依赖 ddgs：DuckDuckGo 在国内基本不可达，且 ddgs 会额外引入
lxml + primp（约 19MB）。Bing 结果页用 curl_cffi 的 chrome 指纹就能稳定拿到。

注意：结果质量取决于会话里的 _EDGE_S cookie 是否带 mkt=zh-CN。预热 cn.bing.com
才能拿到中文市场 cookie；预热 www.bing.com 会拿到国际索引，多词中文 query 只按
头词召回（例如「开源 AI Agent 框架 对比」全变成开源 hub 页）。
"""

import base64
import re
import threading
import urllib.parse

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://cn.bing.com/",
}

SEARCH_ENDPOINT = "https://www.bing.com/search"
HOME_URL = "https://cn.bing.com/"

_sessions = {}
_sessions_lock = threading.Lock()


def _get_session(use_proxy: bool):
    """按路由复用会话：首次先预热 cn.bing.com，拿到 mkt=zh-CN 的中文市场 cookie。"""
    from curl_cffi import requests

    with _sessions_lock:
        if use_proxy not in _sessions:
            session = requests.Session(trust_env=use_proxy)
            try:
                session.get(
                    HOME_URL, headers=DEFAULT_HEADERS, timeout=10, impersonate="chrome"
                )
            except Exception as e:
                print(f"[Search Debug]Bing 首页预热失败: {e}")
            _sessions[use_proxy] = session
        return _sessions[use_proxy]


def _build_search_url(query: str) -> str:
    return f"{SEARCH_ENDPOINT}?q={urllib.parse.quote(query)}&form=QBLH"


def _decode_bing_url(href: str) -> str:
    """还原 bing.com/ck/a 跳转包装里的真实地址；普通链接原样返回。"""
    if "bing.com/ck/a" not in href:
        return href
    try:
        params = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
        payload = params.get("u", [""])[0]
        if not payload.startswith("a1"):
            return href
        raw = payload[2:]
        raw += "=" * (-len(raw) % 4)
        real = base64.urlsafe_b64decode(raw).decode("utf-8", "ignore")
        return real if real.startswith("http") else href
    except Exception:
        return href


def _parse_bing_html(html: str, max_results: int = 5) -> list:
    """解析 Bing 结果页，返回 title/url/snippet 列表。"""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    results = []

    for li in soup.find_all("li", class_="b_algo"):
        if len(results) >= max_results:
            break

        h2 = li.find("h2")
        a = h2.find("a") if h2 else None
        if not a or not a.get("href"):
            continue

        link = _decode_bing_url(a["href"])
        if not link.startswith("http"):
            continue

        p = li.find("p")
        results.append({"title": a.text, "url": link, "snippet": p.text if p else ""})

    return results


def _has_query_overlap(results: list, query: str) -> bool:
    """判断结果是否与 query 有词面重叠，用于识别 Bing 的兜底/降级结果页。"""
    terms = [t for t in re.split(r"\s+", query.strip()) if len(t) >= 2]
    if not terms:
        return True

    haystack = " ".join(
        f"{item['title']} {item['snippet']} {item['url']}" for item in results
    ).lower()
    return any(term.lower() in haystack for term in terms)


def _fetch_html(url: str, use_proxy: bool) -> str:
    session = _get_session(use_proxy)
    response = session.get(
        url, headers=DEFAULT_HEADERS, timeout=10, impersonate="chrome"
    )
    print(f"[Search Debug]Bing HTTP 状态码: {response.status_code} (代理={use_proxy})")
    return response.text


def _bing_search(query: str, max_results: int = 5) -> list:
    """伪装版 Bing 爬虫（使用 chrome 指纹绕过 SSL 拦截）"""
    url = _build_search_url(query)
    print(f"[Search Debug]正在请求 Bing 搜索: {url}")

    fallback = []
    # 先直连（与浏览器一致），失败或结果跑偏再回退系统代理
    for use_proxy in (False, True):
        try:
            html = _fetch_html(url, use_proxy)
        except Exception as e:
            print(f"[Search Debug]Bing 搜索异常: {e}")
            continue

        results = _parse_bing_html(html, max_results)
        print(f"[Search Debug]成功解析到 Bing 有效搜索结果: {len(results)} 条")

        if results and _has_query_overlap(results, query):
            return results
        if results and not fallback:
            fallback = results

    return fallback


def web_search(query: str, max_results: int = 5) -> tuple:
    """纯粹的互联网内容检索"""
    try:
        results = _bing_search(query, max_results)

        if not results:
            return [], "搜索未找到相关结果 (Bing 被拦截或无结果)"

        return results, None

    except Exception as e:
        return [], f"搜索过程异常: {str(e)}"
