"""Web 搜索模块 - 直接抓取 Bing 结果页（与 Fetch 完全解耦）

之所以不再依赖 ddgs：DuckDuckGo 在国内基本不可达，且 ddgs 会额外引入
lxml + primp（约 19MB）。Bing 结果页用 curl_cffi 的 chrome 指纹就能稳定拿到。
"""

import urllib.parse

from bs4 import BeautifulSoup
from curl_cffi import requests

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.bing.com/",
}


def _bing_search(query: str, max_results: int = 5) -> list:
    """伪装版 Bing 爬虫（使用 chrome 指纹绕过 SSL 拦截）"""
    url = f"https://cn.bing.com/search?q={urllib.parse.quote(query)}"
    print(f"[Search Debug] 🌐 正在请求 Bing 搜索: {url}")

    try:
        response = requests.get(
            url, headers=DEFAULT_HEADERS, timeout=10, impersonate="chrome"
        )
        print(f"[Search Debug] 📥 Bing HTTP 状态码: {response.status_code}")

        soup = BeautifulSoup(response.text, "html.parser")

        results = []
        algo_blocks = soup.find_all("li", class_="b_algo")
        print(f"[Search Debug] 🔍 成功解析到 Bing 有效搜索结果: {len(algo_blocks)} 条")

        for li in algo_blocks:
            if len(results) >= max_results:
                break

            h2 = li.find("h2")
            if not h2:
                continue
            a = h2.find("a")
            if not a:
                continue

            title = a.text
            link = a.get("href")
            p = li.find("p")
            snippet = p.text if p else ""

            if link and link.startswith("http"):
                results.append({"title": title, "url": link, "snippet": snippet})

        return results

    except Exception as e:
        print(f"[Search Debug] ❌ Bing 搜索异常: {e}")
        return []


def web_search(query: str, max_results: int = 5) -> tuple:
    """纯粹的互联网内容检索"""
    try:
        results = _bing_search(query, max_results)

        if not results:
            return [], "搜索未找到相关结果 (Bing 被拦截或无结果)"

        return results, None

    except Exception as e:
        return [], f"搜索过程异常: {str(e)}"
