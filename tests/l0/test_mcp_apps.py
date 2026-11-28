"""MCP Apps 旁路存储、上传参数注入与配置指纹（SPEC-025）。"""

from __future__ import annotations

import copy

import pytest

from src.tool.callmcp import mcp_apps
from src.tool.callmcp._shared import config_fingerprint, is_http_config


def test_config_fingerprint_tracks_url_and_headers():
    """SPEC-025 AC-1：HTTP 传输改地址/请求头必须触发重连。"""
    base = {"command": "", "args": [], "env": {}, "url": "http://127.0.0.1:3001/mcp"}
    assert config_fingerprint(base) == config_fingerprint(dict(base))

    moved = dict(base, url="http://127.0.0.1:3002/mcp")
    assert config_fingerprint(moved) != config_fingerprint(base)

    with_header = dict(base, headers={"Authorization": "Bearer x"})
    assert config_fingerprint(with_header) != config_fingerprint(base)

    stdio = {"command": "npx", "args": ["-y", "x"], "env": {}}
    assert config_fingerprint(stdio) == config_fingerprint(dict(stdio))


def test_is_http_config_requires_non_empty_url():
    assert is_http_config({"url": "http://127.0.0.1:3001/mcp"}) is True
    assert is_http_config({"url": "   "}) is False
    assert is_http_config({"command": "npx", "args": []}) is False


def test_ui_resource_uri_reads_meta_only():
    """SPEC-025 AC-2：资源地址只从 _meta.ui.resourceUri 取。"""
    meta = {"ui": {"resourceUri": "ui://cesium-map/mcp-app.html"}}
    assert mcp_apps.ui_resource_uri(meta) == "ui://cesium-map/mcp-app.html"
    assert (
        mcp_apps.ui_resource_uri({"ui/resourceUri": "ui://flat/app.html"})
        == "ui://flat/app.html"
    )
    assert mcp_apps.ui_resource_uri({"ui": {}}) is None
    assert mcp_apps.ui_resource_uri({"ui": {"resourceUri": 42}}) is None
    assert mcp_apps.ui_resource_uri(None) is None
    assert mcp_apps.ui_resource_uri("nope") is None


@pytest.mark.parametrize(
    "app_id, expected",
    [
        ("call_abc-123", True),
        ("", False),
        ("../escape", False),
        ("a/b", False),
        ("x" * 129, False),
        ("x" * 128, True),
    ],
)
def test_is_legal_app_id_blocks_traversal(app_id, expected):
    """SPEC-025 AC-3：app id 必须是单段安全文件名。"""
    assert mcp_apps.is_legal_app_id(app_id) is expected


def test_save_and_load_roundtrip(tmp_path, monkeypatch):
    """SPEC-025 AC-3/AC-5：HTML 与元数据分离存放，可分别取回。"""
    monkeypatch.setattr(mcp_apps, "BUFFER_DIR", str(tmp_path))

    payload = {
        "server": "cesium-map",
        "tool": "show-map",
        "uri": "ui://cesium-map/mcp-app.html",
        "arguments": {"west": -1},
        "result": {"content": [{"type": "text", "text": "ok"}]},
    }
    assert mcp_apps.save_app("call_1", payload, "<html>app</html>") is True
    assert mcp_apps.has_app("call_1") is True
    assert mcp_apps.has_app("../call_1") is False
    assert mcp_apps.load_html("call_1") == "<html>app</html>"
    assert mcp_apps.load_payload("call_1")["tool"] == "show-map"
    assert mcp_apps.has_app("call_missing") is False
    assert mcp_apps.load_html("../call_1") is None


def test_save_app_rejects_illegal_id(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_apps, "BUFFER_DIR", str(tmp_path))
    assert mcp_apps.save_app("../x", {"server": "s"}, "<html></html>") is False
    assert not (tmp_path / "mcp_apps").exists()


def test_attach_history_apps_marks_only_backed_tool_messages(tmp_path, monkeypatch):
    """SPEC-025 AC-4：不改入参，只标注存在旁路文件的 tool 消息。"""
    monkeypatch.setattr(mcp_apps, "BUFFER_DIR", str(tmp_path))
    mcp_apps.save_app(
        "call_1",
        {
            "server": "cesium-map",
            "tool": "show-map",
            "uri": "ui://cesium-map/mcp-app.html",
        },
        "<html></html>",
    )

    messages = [
        {"role": "user", "content": "hi"},
        {"role": "tool", "tool_call_id": "call_1", "name": "CallMCP", "content": "{}"},
        {"role": "tool", "tool_call_id": "call_2", "name": "CallMCP", "content": "{}"},
        {"role": "tool", "name": "CallMCP", "content": "{}"},
    ]
    snapshot = copy.deepcopy(messages)

    out = mcp_apps.attach_history_apps(messages)

    assert messages == snapshot  # 入参不被污染，避免写回磁盘
    assert "mcp_app" not in out[0]
    assert out[1]["mcp_app"] == {
        "id": "call_1",
        "server": "cesium-map",
        "tool": "show-map",
        "uri": "ui://cesium-map/mcp-app.html",
    }
    assert "mcp_app" not in out[2]
    assert "mcp_app" not in out[3]
    assert out[1]["content"] == "{}"


def test_with_system_arguments_injects_tool_call_id_for_callmcp():
    """SPEC-025：CallMCP 需要 tool_call_id 才能把 App 挂到对应消息。"""
    from src.agent.tool_calls import with_system_arguments

    assert with_system_arguments(
        "CallMCP", {"server_name": "s"}, session_id="x", tool_call_id="call_1"
    ) == {"server_name": "s", "_tool_call_id": "call_1"}
    assert with_system_arguments(
        "Bash", {"command": "ls"}, session_id="s1", tool_call_id="call_1"
    ) == {"command": "ls", "session_id": "s1"}


def test_save_result_roundtrip_and_attach_data(tmp_path, monkeypatch):
    """SPEC-025 AC-9：无 UI 工具的结构化结果按 tool_call_id 落盘并附加到历史。"""
    monkeypatch.setattr(mcp_apps, "BUFFER_DIR", str(tmp_path))

    data = {
        "server": "demo",
        "tool": "search",
        "structuredContent": {"items": [{"id": 1}, {"id": 2}]},
    }
    assert mcp_apps.save_result("call_1", data) is True
    assert mcp_apps.save_result("../x", data) is False
    assert mcp_apps.load_result("call_1") == data
    assert mcp_apps.load_result("call_missing") is None

    messages = [{"role": "tool", "tool_call_id": "call_1", "content": "[]"}]
    out = mcp_apps.attach_history_apps(messages)
    assert "mcp_app" not in out[0]
    assert out[0]["mcp_data"] == data
    assert "mcp_data" not in messages[0]
