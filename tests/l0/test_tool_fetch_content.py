"""Fetch 内容处理：编码、HTML→文本与原始内容裁剪（SPEC-022 AC-2）。"""

from __future__ import annotations

from src.tool.fetch import _shared


def test_detect_charset_reads_header_and_falls_back():
    """SPEC-022 AC-2：从 Content-Type 解析 charset，缺失时回落默认值。"""
    assert _shared.detect_charset("text/html; charset=UTF-8") == "UTF-8"
    assert _shared.detect_charset("text/html; charset=gbk") == "gbk"
    # 带引号的 charset 不在原实现识别范围内，保持回落到默认值
    assert _shared.detect_charset('application/json; charset="gbk"') == "utf-8"
    assert _shared.detect_charset("text/html") == "utf-8"
    assert _shared.detect_charset(None, default="gbk") == "gbk"


def test_decode_bytes_uses_charset_and_falls_back_to_utf8():
    """SPEC-022 AC-2：未知编码不抛异常，按 UTF-8 替换解码。"""
    assert _shared.decode_bytes("中文".encode("gbk"), "gbk") == "中文"
    assert _shared.decode_bytes("中文".encode("utf-8"), "utf-8") == "中文"
    assert _shared.decode_bytes(b"\xff", "no-such-charset") == "\ufffd"


def test_clip_bytes_truncates_to_limit():
    """SPEC-022 AC-2：响应体按字节上限裁剪。"""
    assert _shared.clip_bytes(b"abcdef", 3) == b"abc"
    assert _shared.clip_bytes(b"abc", 10) == b"abc"
    assert _shared.clip_bytes(b"", 10) == b""


def test_looks_like_raw_text_url_matches_hosts_and_suffixes():
    """SPEC-022 AC-2：原始文本地址按域名与后缀快速识别。"""
    assert _shared.looks_like_raw_text_url("https://raw.githubusercontent.com/a/b.py")
    assert _shared.looks_like_raw_text_url("https://example.com/data.json?download=1")
    assert not _shared.looks_like_raw_text_url("https://example.com/article")


def test_build_raw_text_result_markdown_is_returned_verbatim():
    """SPEC-022 AC-2：Markdown 原始内容不加代码围栏。"""
    result = _shared.build_raw_text_result(
        "https://example.com/readme.md", "# 标题", "text/markdown"
    )

    assert result == {
        "url": "https://example.com/readme.md",
        "title": "raw: readme.md",
        "content": "# 标题",
        "content_type": "markdown",
    }


def test_build_raw_text_result_uses_fenced_language_and_title_suffix():
    """SPEC-022 AC-2：代码类后缀加语言围栏，标题附带内容类型。"""
    py = _shared.build_raw_text_result(
        "https://example.com/main.py", "print(1)", "text/plain; charset=utf-8"
    )
    assert py["content"] == "```python\nprint(1)\n```"
    assert py["title"] == "raw: main.py (text/plain)"

    plain = _shared.build_raw_text_result("https://example.com/blob", "abc", "")
    assert plain["content"] == "```\nabc\n```"
    assert plain["content_type"] == "text"


def test_html_to_markdown_prefers_main_and_strips_noise():
    """SPEC-022 AC-2：优先 main/article，去掉导航与页脚。"""
    html = (
        "<html><head><title>示例</title></head><body>"
        "<nav>菜单</nav><main><h1>标题</h1><p>正文内容</p></main>"
        "<footer>页脚</footer></body></html>"
    )

    title, text = _shared.html_to_markdown(html, "https://example.com")

    assert title == "示例"
    assert "标题" in text and "正文内容" in text
    assert "菜单" not in text and "页脚" not in text


def test_html_to_markdown_falls_back_to_paragraphs_when_too_short():
    """SPEC-022 AC-2：正文过短时退化为段落汇总，仍保留有效文本。"""
    html = "<html><body><div>第一段</div><div>第二段</div></body></html>"

    title, text = _shared.html_to_markdown(html, "https://example.com/no-title")

    assert title == "https://example.com/no-title"
    assert "第一段" in text and "第二段" in text
