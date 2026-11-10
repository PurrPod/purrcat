"""工具输出超长截断：落盘、预览与 vision 例外（SPEC-005）。"""

from __future__ import annotations

import json

from src.tool.utils import route
from src.tool.utils.token_limit import (
    DEFAULT_OUTPUT_TOKEN_LIMIT,
    MIN_OUTPUT_TOKEN_LIMIT,
    get_output_token_limit,
)


def _stub_tool(monkeypatch, result):
    monkeypatch.setattr(route, "resolve_tool", lambda name: lambda **kwargs: result)


def test_token_limit_boundaries():
    assert get_output_token_limit() == DEFAULT_OUTPUT_TOKEN_LIMIT
    assert get_output_token_limit(-100) == MIN_OUTPUT_TOKEN_LIMIT
    assert (
        get_output_token_limit(MIN_OUTPUT_TOKEN_LIMIT + 100) == MIN_OUTPUT_TOKEN_LIMIT
    )
    assert get_output_token_limit(2000) == 1500
    assert get_output_token_limit(10**9) == DEFAULT_OUTPUT_TOKEN_LIMIT


def test_long_output_is_buffered_truncated_and_wrapped(tmp_path, monkeypatch):
    monkeypatch.setattr(route, "BUFFER_DIR", str(tmp_path))
    text = "字" * 5000
    _stub_tool(monkeypatch, text)

    payload = json.loads(route.dispatch_tool("Echo", {}, available_tokens=1000))

    assert payload["metadata"]["type"] == "warning"
    assert "落盘" in payload["metadata"]["snip"]
    assert payload["content"].startswith("⚠️ [系统拦截]")
    assert "沙盒内路径: /agent_vm/.buffer/echo/" in payload["content"]

    files = list((tmp_path / "echo").iterdir())
    assert len(files) == 1
    assert files[0].read_text(encoding="utf-8") == text


def test_short_output_passes_through_without_buffer(tmp_path, monkeypatch):
    monkeypatch.setattr(route, "BUFFER_DIR", str(tmp_path))
    _stub_tool(monkeypatch, {"content": "ok", "metadata": {"type": "text", "snip": ""}})

    payload = json.loads(route.dispatch_tool("Echo", {}, available_tokens=1000))

    assert payload["content"] == "ok"
    assert payload["metadata"]["type"] == "text"
    assert not (tmp_path / "echo").exists()


def test_vision_parts_skip_truncation_and_merge_snip(tmp_path, monkeypatch):
    monkeypatch.setattr(route, "BUFFER_DIR", str(tmp_path))
    parts = [
        {"type": "text", "text": "图片如下"},
        {
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64," + "A" * 100000},
        },
    ]
    _stub_tool(
        monkeypatch,
        {"content": parts, "metadata": {"type": "text", "snip": "关键提示"}},
    )

    payload = json.loads(route.dispatch_tool("Echo", {}, available_tokens=1))

    assert isinstance(payload["content"], list)
    assert payload["metadata"]["type"] == "text"
    assert payload["content"][0]["text"] == "图片如下\n关键提示"
    assert not any(tmp_path.iterdir())


def test_tool_exception_returns_error_payload(monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("炸了")

    monkeypatch.setattr(route, "resolve_tool", lambda name: boom)

    payload = json.loads(route.dispatch_tool("Echo", {}))

    assert payload["metadata"]["type"] == "error"
    assert "炸了" in payload["content"]


def test_unresolvable_tool_returns_error_payload(monkeypatch):
    def missing(name):
        raise ImportError(f"no tool named {name}")

    monkeypatch.setattr(route, "resolve_tool", missing)

    payload = json.loads(route.dispatch_tool("Ghost", {}))

    assert payload["metadata"]["type"] == "error"
    assert "Ghost" in payload["content"]
