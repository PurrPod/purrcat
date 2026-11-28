"""Web 搜索：Bing 结果页解析（不触网）。"""

from __future__ import annotations

import base64

import src.tool.search.web_search as ws
from src.tool.search.web_search import (
    _bing_search,
    _build_search_url,
    _decode_bing_url,
    _parse_bing_html,
    _query_terms,
    _relevance,
    web_search,
)


def _wrap(real_url: str) -> str:
    payload = base64.urlsafe_b64encode(real_url.encode()).decode().rstrip("=")
    return f"https://www.bing.com/ck/a?!&&p=abc&ptn=3&u=a1{payload}&ntb=1"


HTML = f"""
<html><body><ol>
  <li class="b_algo">
    <h2><a href="https://example.com/direct">直接链接</a></h2>
    <p>直接摘要</p>
  </li>
  <li class="b_algo">
    <h2><a href="{_wrap("https://zhuanlan.zhihu.com/p/1885618917550057149")}">跳转包装链接</a></h2>
    <p>包装摘要</p>
  </li>
  <li class="b_algo"><h2>没有链接</h2></li>
  <li class="b_algo">
    <h2><a href="https://example.com/third">第三条</a></h2>
  </li>
</ol></body></html>
"""


def test_parse_returns_real_urls():
    results = _parse_bing_html(HTML, max_results=5)

    assert [item["url"] for item in results] == [
        "https://example.com/direct",
        "https://zhuanlan.zhihu.com/p/1885618917550057149",
        "https://example.com/third",
    ]
    assert results[0]["title"] == "直接链接"
    assert results[0]["snippet"] == "直接摘要"
    assert results[1]["snippet"] == "包装摘要"
    assert results[2]["snippet"] == ""


def test_parse_respects_max_results():
    assert len(_parse_bing_html(HTML, max_results=2)) == 2


def test_decode_passthrough_for_plain_url():
    assert _decode_bing_url("https://example.com/a") == "https://example.com/a"


def test_decode_keeps_wrapper_when_payload_invalid():
    broken = "https://www.bing.com/ck/a?!&&u=a1!!!notbase64!!!"
    assert _decode_bing_url(broken) == broken


def test_build_search_url_matches_browser_shape():
    """与浏览器一致：cn.bing.com、只有 q 参数。"""
    url = _build_search_url("2025年 开源大模型排行")

    assert url.startswith("https://cn.bing.com/search?q=")
    assert "mkt=" not in url
    assert "2025%E5%B9%B4" in url


def test_overlap_detects_relevant_results():
    results = [{"title": "PurrCat Agent 框架", "url": "", "snippet": ""}]

    assert _relevance(results, "PurrCat Agent 框架") >= 0.5


def test_overlap_flags_bing_fallback_page():
    """兜底页示例：查开源大模型排行却返回日历、统计公报。"""
    results = [
        {
            "title": "万年历2025年日历表",
            "url": "https://www.rili.com.cn/",
            "snippet": "",
        },
        {"title": "抖音-记录美好生活", "url": "https://www.douyin.com/", "snippet": ""},
    ]

    assert _relevance(results, "开源大模型排行") < 0.5


def test_overlap_skips_single_char_terms():
    results = [{"title": "任意结果", "url": "https://example.com", "snippet": ""}]

    assert _relevance(results, "a 的") == 1.0


def test_query_terms_split_unspaced_cjk_query():
    terms = _query_terms("langgraph和crewai的区别")

    assert "langgraph" in terms
    assert "crewai" in terms
    assert "区别" in terms


def test_head_term_results_are_low_relevance():
    """头词降级页：query 里只有 langgraph 出现在结果中。"""
    results = [
        {
            "title": "LangGraph - LangChain 框架",
            "url": "https://langgraph.com.cn",
            "snippet": "",
        },
        {
            "title": "LangGraph 入门教程 | 菜鸟教程",
            "url": "https://runoob.com",
            "snippet": "",
        },
    ]

    assert _relevance(results, "langgraph 和 crewai 区别") < 0.5
    assert _relevance(results, "langgraph 和 crewai 区别") < 0.5


GOOD_HTML = """
<html><body><ol>
  <li class="b_algo">
    <h2><a href="https://github.com/PurrPod/purrcat">PurrCat Agent 框架</a></h2>
  </li>
</ol></body></html>
"""

BAD_HTML = """
<html><body><ol>
  <li class="b_algo"><h2><a href="https://www.douyin.com/">抖音-记录美好生活</a></h2></li>
  <li class="b_algo"><h2><a href="https://www.rili.com.cn/">万年历2025年日历表</a></h2></li>
</ol></body></html>
"""


PROXY = "http://127.0.0.1:7897"


def test_bing_search_uses_direct_route_first(monkeypatch):
    calls = []

    def fake_fetch(url, proxy):
        calls.append(proxy)
        return GOOD_HTML

    monkeypatch.setattr(ws, "_detect_proxy", lambda: PROXY)
    monkeypatch.setattr(ws, "_fetch_html", fake_fetch)

    results = _bing_search("PurrCat Agent 框架", 5)

    assert calls == [""]
    assert results[0]["url"] == "https://github.com/PurrPod/purrcat"


def test_bing_search_retries_through_proxy_when_direct_degrades(monkeypatch):
    calls = []

    def fake_fetch(url, proxy):
        calls.append(proxy)
        return GOOD_HTML if proxy else BAD_HTML

    monkeypatch.setattr(ws, "_detect_proxy", lambda: PROXY)
    monkeypatch.setattr(ws, "_fetch_html", fake_fetch)

    results = _bing_search("PurrCat Agent 框架", 5)

    assert calls == ["", PROXY]
    assert results[0]["title"] == "PurrCat Agent 框架"


def test_bing_search_skips_proxy_when_none_is_available(monkeypatch):
    calls = []

    def fake_fetch(url, proxy):
        calls.append(proxy)
        return BAD_HTML

    monkeypatch.setattr(ws, "_detect_proxy", lambda: "")
    monkeypatch.setattr(ws, "_fetch_html", fake_fetch)

    _bing_search("PurrCat Agent 框架", 5)

    assert calls == [""]


def test_bing_search_returns_best_attempt_when_every_route_degrades(monkeypatch):
    def fake_fetch(url, proxy):
        return BAD_HTML

    monkeypatch.setattr(ws, "_detect_proxy", lambda: PROXY)
    monkeypatch.setattr(ws, "_fetch_html", fake_fetch)

    results = _bing_search("PurrCat Agent 框架", 5)

    assert [item["title"] for item in results] == [
        "抖音-记录美好生活",
        "万年历2025年日历表",
    ]


def test_web_search_returns_error_when_nothing_is_parsed(monkeypatch):
    monkeypatch.setattr(ws, "_bing_search", lambda q, n: [])

    results, error = web_search("PurrCat Agent 框架", 5)

    assert results == []
    assert error
