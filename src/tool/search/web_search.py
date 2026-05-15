"""Web 搜索模块 - 国内外自适应 + 防拦截终极版 (与 Fetch 完全解耦)"""

import urllib.parse
from bs4 import BeautifulSoup
from curl_cffi import requests

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.bing.com/"
}


def _duckduckgo_search(query: str, max_results: int = 5) -> list:
    """策略一：外网首选 DuckDuckGo"""
    print("\n[Search Debug] 🦆 正在尝试 DuckDuckGo 搜索...")
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
            if results:
                print(f"[Search Debug] 🦆 DuckDuckGo 搜索成功，获取到 {len(results)} 条结果！")
            return [
                {
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", "")
                }
                for r in results
            ]
    except ImportError:
        print("[Search Debug] ⚠️ 未安装 ddgs 库，跳过...")
        return []
    except Exception as e:
        print(f"[Search Debug] ❌ DuckDuckGo 搜索异常: {e}")
        return []


def _bing_search(query: str, max_results: int = 5) -> list:
    """策略二：伪装版 Bing 爬虫（使用 chrome 指纹绕过 SSL 拦截）"""
    url = f"https://cn.bing.com/search?q={urllib.parse.quote(query)}"
    print(f"[Search Debug] 🌐 正在降级至 Bing 搜索: {url}")

    try:
        response = requests.get(url, headers=DEFAULT_HEADERS, timeout=10, impersonate="chrome")
        print(f"[Search Debug] 📥 Bing HTTP 状态码: {response.status_code}")

        soup = BeautifulSoup(response.text, 'html.parser')

        results = []
        algo_blocks = soup.find_all('li', class_='b_algo')
        print(f"[Search Debug] 🔍 成功解析到 Bing 有效搜索结果: {len(algo_blocks)} 条")

        for li in algo_blocks:
            if len(results) >= max_results:
                break

            h2 = li.find('h2')
            if not h2:
                continue
            a = h2.find('a')
            if not a:
                continue

            title = a.text
            link = a.get('href')
            p = li.find('p')
            snippet = p.text if p else ""

            if link and link.startswith("http"):
                results.append({
                    "title": title,
                    "url": link,
                    "snippet": snippet
                })

        return results

    except Exception as e:
        print(f"[Search Debug] ❌ Bing 搜索也发生报错: {e}")
        return []


def web_search(query: str, max_results: int = 5) -> tuple:
    """纯粹的互联网内容检索 (自适应主备版)"""
    try:
        results = _duckduckgo_search(query, max_results)

        if not results:
            print("[Search Debug] ⚠️ 触发降级策略...")
            results = _bing_search(query, max_results)

        if not results:
            return [], "搜索未找到相关结果 (DuckDuckGo 与 Bing 均被拦截或无结果)"

        return results, None

    except Exception as e:
        return [], f"搜索过程异常: {str(e)}"