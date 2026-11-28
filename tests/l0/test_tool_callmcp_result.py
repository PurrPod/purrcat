"""CallMCP 结果落盘：只认协议显式的 structuredContent。"""

from __future__ import annotations

import asyncio

from src.tool.callmcp import mcp_apps, tool_caller


class _Text:
    type = "text"

    def __init__(self, text):
        self.text = text


class _Result:
    isError = False

    def __init__(self, text, structured=None):
        self.content = [_Text(text)]
        self.structuredContent = structured


class _Session:
    def __init__(self, result):
        self._result = result

    async def call_tool(self, name, arguments):
        return self._result


def _invoke(monkeypatch, result):
    saved = {}

    def fake_save(tool_call_id, payload):
        saved[tool_call_id] = payload
        return True

    monkeypatch.setattr(tool_caller, "load_configs", lambda: {"calculator": {}})
    monkeypatch.setattr(tool_caller, "_tool_ui_resource", lambda *_: None)
    monkeypatch.setattr(mcp_apps, "save_result", fake_save)
    monkeypatch.setattr(mcp_apps, "is_legal_app_id", lambda _id: True)

    async def fake_get_session(server, config):
        return _Session(result)

    monkeypatch.setattr(tool_caller.mcp_manager, "get_session", fake_get_session)
    asyncio.run(tool_caller._invoke_tool_async("calculator", "calculate", {}, "call_1"))
    return saved


def test_json_text_is_not_treated_as_structured_content(monkeypatch):
    """普通 JSON 文本是普通结果，不应被当成 structuredContent 落盘。"""
    saved = _invoke(monkeypatch, _Result('{"result": 1030}'))
    assert saved == {}


def test_protocol_structured_content_is_saved(monkeypatch):
    saved = _invoke(monkeypatch, _Result("ok", {"items": []}))
    assert saved["call_1"]["structuredContent"] == {"items": []}
