"""Web 搜索模块 - 直接抓取 Bing 结果页（与 Fetch 完全解耦）

之所以不再依赖 ddgs：DuckDuckGo 在国内基本不可达，且 ddgs 会额外引入
lxml + primp（约 19MB）。Bing 结果页用 curl_cffi 的 chrome 指纹就能稳定拿到。

结果质量取决于 Bing 的出口地区：从国内 IP 直连返回"国内版"索引，多实体中文
query 只按首个词召回（「langgraph 和 crewai 区别」只返回 LangGraph）；走境外
出口则返回国际索引。因此先直连，覆盖率不足时再经本机代理重试。
"""

import base64
import os
import re
import socket
import threading
import urllib.parse

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://cn.bing.com/",
}

SEARCH_ENDPOINT = "https://cn.bing.com/search"
HOME_URL = "https://cn.bing.com/"

# libcurl 会自己读 HTTP(S)_PROXY/ALL_PROXY，直连必须显式传空值覆盖
DIRECT = {"http": "", "https": ""}

# 本机代理端口：Clash(7897/7890)、v2rayN(10809)
PROXY_PORTS = (7897, 7890, 10809)

# query 词覆盖率低于该阈值时，视为 Bing 头词降级页，改走代理重试
MIN_RELEVANCE = 0.5

# 匹配英文词与中文连续片段。中文无空格，整串匹配几乎必然失配，故按二元组切分；
# 单字和"的/和/与"这类虚词会命中任意标题，会虚高覆盖率，先剔除。
TERM_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.+-]*|[\u4e00-\u9fff]+")
STOPWORDS = {"的", "和", "与", "或", "是", "在", "了", "吗", "呢"}

_sessions = {}
_sessions_lock = threading.Lock()
_proxy = ""
_proxy_ready = False


def _detect_proxy() -> str:
    """探测本机代理：显式环境变量 → 系统代理设置 → 常见本机端口。"""
    global _proxy, _proxy_ready
    if _proxy_ready:
        return _proxy

    for key in (
        "PURRCAT_SEARCH_PROXY",
        "HTTPS_PROXY",
        "https_proxy",
        "HTTP_PROXY",
        "http_proxy",
        "ALL_PROXY",
        "all_proxy",
    ):
        value = os.environ.get(key)
        if value:
            _proxy = value
            _proxy_ready = True
            return _proxy

    try:
        import winreg

        path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            enabled, _ = winreg.QueryValueEx(key, "ProxyEnable")
            server, _ = winreg.QueryValueEx(key, "ProxyServer")
        if enabled and server:
            proxy = server.split(";")[0].split("=")[-1]
            _proxy = proxy if "://" in proxy else f"http://{proxy}"
            _proxy_ready = True
            return _proxy
    except Exception:
        pass

    for port in PROXY_PORTS:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.05):
                _proxy = f"http://127.0.0.1:{port}"
                _proxy_ready = True
                return _proxy
        except OSError:
            continue

    _proxy = ""
    _proxy_ready = True
    return _proxy


def _proxies(proxy: str) -> dict:
    return dict(DIRECT) if not proxy else {"http": proxy, "https": proxy}


def _get_session(proxy: str):
    """按出口复用会话：首次先预热 cn.bing.com，拿到中文市场 cookie。"""
    from curl_cffi import requests

    with _sessions_lock:
        if proxy not in _sessions:
            session = requests.Session()
            try:
                session.get(
                    HOME_URL,
                    headers=DEFAULT_HEADERS,
                    timeout=10,
                    impersonate="chrome",
                    proxies=_proxies(proxy),
                )
            except Exception as e:
                print(f"[Search Debug]Bing 首页预热失败: {e}")
            _sessions[proxy] = session
        return _sessions[proxy]


def _build_search_url(query: str) -> str:
    # 与浏览器一致：主机、路径、参数都取最简形式
    return f"{SEARCH_ENDPOINT}?q={urllib.parse.quote(query)}"


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


def _query_terms(query: str) -> list:
    terms = []
    for chunk in TERM_RE.findall(query):
        if chunk[0].isascii():
            if len(chunk) >= 2 and chunk.lower() not in STOPWORDS:
                terms.append(chunk.lower())
            continue
        if len(chunk) < 2:
            continue
        if len(chunk) == 2:
            terms.append(chunk)
            continue
        terms.extend(chunk[i : i + 2] for i in range(len(chunk) - 1))
    return terms


def _relevance(results: list, query: str) -> float:
    """结果覆盖了多少 query 词，0~1；用于识别 Bing 的头词降级结果页。"""
    terms = _query_terms(query)
    if not terms:
        return 1.0

    haystack = " ".join(
        f"{item['title']} {item['snippet']} {item['url']}" for item in results
    ).lower()
    return sum(1 for term in terms if term in haystack) / len(terms)


def _fetch_html(url: str, proxy: str) -> str:
    session = _get_session(proxy)
    response = session.get(
        url,
        headers=DEFAULT_HEADERS,
        timeout=10,
        impersonate="chrome",
        proxies=_proxies(proxy),
    )
    print(
        f"[Search Debug]Bing HTTP 状态码: {response.status_code}"
        f" (出口={proxy or '直连'})"
    )
    return response.text


def _bing_search(query: str, max_results: int = 5) -> list:
    """伪装版 Bing 爬虫（使用 chrome 指纹绕过 SSL 拦截）"""
    url = _build_search_url(query)
    print(f"[Search Debug]正在请求 Bing 搜索: {url}")

    proxy = _detect_proxy()
    best = []
    best_score = -1.0

    # 先直连；结果只命中首个词时改走本机代理（境外出口的国际索引）
    for candidate in ("", proxy) if proxy else ("",):
        try:
            html = _fetch_html(url, candidate)
        except Exception as e:
            print(f"[Search Debug]Bing 搜索异常: {e}")
            continue

        results = _parse_bing_html(html, max_results)
        score = _relevance(results, query) if results else 0.0
        print(f"[Search Debug]成功解析到 Bing 有效搜索结果: {len(results)} 条")

        if results and score > best_score:
            best, best_score = results, score
        if score >= MIN_RELEVANCE:
            return results

    return best


def web_search(query: str, max_results: int = 5) -> tuple:
    """纯粹的互联网内容检索"""
    try:
        results = _bing_search(query, max_results)

        if not results:
            return [], "搜索未找到相关结果 (Bing 被拦截或无结果)"

        return results, None

    except Exception as e:
        return [], f"搜索过程异常: {str(e)}"
