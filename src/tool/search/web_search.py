"""Web 搜索模块 - 使用 Tavily 或 DuckDuckGo 进行互联网搜索"""

import requests
from typing import List, Dict


def web_search(query: str, max_results: int = 5) -> tuple:
    """
    搜索互联网内容并返回结构化结果
    
    优先使用 Tavily API（需配置 web_api.tavily_api_key），
    无可用 API 时降级到 DuckDuckGo。
    
    Args:
        query: 搜索查询词
        max_results: 最大返回结果数，默认 5
    
    Returns:
        (results, error_message) - results 为搜索结果列表，error_message 为错误信息（成功时为 None）
    """
    results = []
    error_logs = []
    
    # 优先级 1: Tavily API
    from src.utils.config import get_model_config
    tavily_key = get_model_config().get("web", {}).get("tavily_api_key", "")
    
    if tavily_key:
        try:
            data = {"api_key": tavily_key, "query": query, "search_depth": "basic", "max_results": max_results}
            resp = requests.post("https://api.tavily.com/search", json=data, timeout=10)
            if resp.status_code == 200:
                for res in resp.json().get("results", []):
                    results.append({
                        "title": res["title"],
                        "url": res["url"],
                        "snippet": res["content"]
                    })
            else:
                error_logs.append(f"Tavily API Error: {resp.status_code}")
        except Exception as e:
            error_logs.append(f"Tavily Exception: {str(e)}")
    
    # 优先级 2: DuckDuckGo (no API key needed)
    if not results:
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=max_results):
                    results.append({
                        "title": r.get("title", ""),
                        "url": r.get("href", ""),
                        "snippet": r.get("body", "")
                    })
        except ImportError:
            error_logs.append("DuckDuckGo not available (install duckduckgo_search)")
        except Exception as e:
            error_logs.append(f"DDGS Exception: {str(e)}")
    
    if not results:
        return [], f"所有搜索源均失败: {', '.join(error_logs)}"
    
    return results, None