"""Web 搜索：Bing 结果页解析（不触网）。"""

from __future__ import annotations

import base64

import src.tool.search.web_search as ws
from src.tool.search.web_search import (
    _bing_search,
    _build_search_url,
    _decode_bing_url,
    _has_query_overlap,
    _parse_bing_html,
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


def test_build_search_url_avoids_cn_market():
    """cn.bing.com 会 302 到 mkt=zh-CN 兜底页，必须直连 www.bing.com。"""
    url = _build_search_url("2025年 开源大模型排行")

    assert url.startswith("https://www.bing.com/search?")
    assert "cn.bing.com" not in url
    assert "mkt=" not in url
    assert "2025%E5%B9%B4" in url


def test_overlap_detects_relevant_results():
    results = [{"title": "PurrCat Agent 框架", "url": "", "snippet": ""}]

    assert _has_query_overlap(results, "PurrCat Agent 框架") is True


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

    assert _has_query_overlap(results, "开源大模型排行") is False


def test_overlap_skips_single_char_terms():
    results = [{"title": "任意结果", "url": "https://example.com", "snippet": ""}]

    assert _has_query_overlap(results, "a 的") is True


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


def test_bing_search_uses_direct_route_first(monkeypatch):
    calls = []

    def fake_fetch(url, use_proxy):
        calls.append(use_proxy)
        return GOOD_HTML

    monkeypatch.setattr(ws, "_fetch_html", fake_fetch)

    results = _bing_search("PurrCat Agent 框架", 5)

    assert calls == [False]
    assert results[0]["url"] == "https://github.com/PurrPod/purrcat"


def test_bing_search_falls_back_to_proxy_when_results_are_degraded(monkeypatch):
    calls = []

    def fake_fetch(url, use_proxy):
        calls.append(use_proxy)
        return BAD_HTML if use_proxy is False else GOOD_HTML

    monkeypatch.setattr(ws, "_fetch_html", fake_fetch)

    results = _bing_search("PurrCat Agent 框架", 5)

    assert calls == [False, True]
    assert results[0]["title"] == "PurrCat Agent 框架"


def test_bing_search_returns_direct_results_when_both_routes_are_off(monkeypatch):
    def fake_fetch(url, use_proxy):
        return BAD_HTML

    monkeypatch.setattr(ws, "_fetch_html", fake_fetch)

    results = _bing_search("PurrCat Agent 框架", 5)

    assert [item["title"] for item in results] == [
        "抖音-记录美好生活",
        "万年历2025年日历表",
    ]
