"""ACP 工具词汇与事件翻译（SPEC-010）。"""

from __future__ import annotations

import json

from src.server.acp.tool_vocab import (
    tool_kind,
    tool_locations,
    tool_raw,
    tool_title,
    vision_text_parts,
)
from src.server.acp.updates import to_updates


def test_tool_kind_maps_builtin_and_filesystem_actions():
    assert tool_kind("Bash", {}) == "execute"
    assert tool_kind("Search", {}) == "search"
    assert tool_kind("FileSystem", {"action": "write"}) == "edit"
    assert tool_kind("FileSystem", {"action": "glob"}) == "search"
    assert tool_kind("FileSystem", {"action": "unknown"}) == "other"
    assert tool_kind("Unknown", {}) == "other"


def test_tool_title_summarizes_key_arguments():
    assert (
        tool_title("FileSystem", {"action": "read", "path": "/agent_vm/a/b.md"})
        == "FileSystem read b.md"
    )
    assert tool_title("Bash", {"command": "ls"}) == "Bash ls"
    assert tool_title("Memo", {"action": "search", "query": {"prompt": "主题"}}) == (
        "Memo search 主题"
    )
    assert tool_title("Unknown", {}) == "Unknown"


def test_tool_locations_only_for_filesystem_with_path():
    assert tool_locations("Bash", {"path": "/agent_vm/a"}) == []
    assert tool_locations("FileSystem", {}) == []

    locations = tool_locations("FileSystem", {"path": "/agent_vm/a.txt"})
    assert len(locations) == 1
    assert "a.txt" in locations[0]["path"]


def test_tool_raw_omits_oversized_arguments():
    assert tool_raw({"a": 1}) == {"a": 1}
    assert tool_raw({}) is None
    assert tool_raw({"text": "字" * 4000}) is None


def test_vision_text_parts_extracts_only_text():
    parts = [
        {"type": "text", "text": "说明"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAA"}},
    ]

    assert vision_text_parts(parts) == "说明"


def test_to_updates_agent_message_has_message_id():
    updates = to_updates({"type": "agent_message", "data": {"text": "你好"}})

    assert len(updates) == 1
    update = updates[0]["params"]["update"]
    assert update["sessionUpdate"] == "agent_message_chunk"
    assert update["messageId"].startswith("msg_")
    assert update["content"]["text"] == "你好"


def test_to_updates_tool_call_emits_three_stage_flow():
    result = json.dumps(
        {
            "content": "done",
            "metadata": {"type": "text", "snip": ""},
        },
        ensure_ascii=False,
    )

    updates = to_updates(
        {
            "type": "tool_call",
            "data": {"name": "Bash", "arguments": {"command": "ls"}, "result": result},
        }
    )

    assert [u["params"]["update"]["sessionUpdate"] for u in updates] == [
        "tool_call",
        "tool_call_update",
        "tool_call_update",
    ]
    first = updates[0]["params"]["update"]
    assert first["status"] == "pending"
    assert first["kind"] == "execute"
    assert first["rawInput"] == {"command": "ls"}
    assert updates[1]["params"]["update"]["status"] == "in_progress"
    completed = updates[2]["params"]["update"]
    assert completed["status"] == "completed"
    assert completed["content"][0]["content"]["text"] == "done"
    assert completed["rawOutput"]["content"] == "done"


def test_to_updates_tool_call_marks_error_as_failed():
    result = json.dumps(
        {"content": "炸了", "metadata": {"type": "error"}}, ensure_ascii=False
    )

    updates = to_updates(
        {"type": "tool_call", "data": {"name": "Bash", "result": result}}
    )

    assert updates[2]["params"]["update"]["status"] == "failed"


def test_to_updates_vision_result_hides_base64():
    updates = to_updates(
        {
            "type": "tool_call",
            "data": {
                "name": "Task",
                "result": [
                    {"type": "text", "text": "图片"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:image/png;base64,AAA"},
                    },
                ],
            },
        }
    )

    body = updates[2]["params"]["update"]["content"][0]["content"]["text"]
    assert body == "图片"


def test_to_updates_usage_and_turn_end_shapes():
    usage = to_updates({"type": "usage", "data": {"used": 5, "size": 10}})
    assert usage[0]["params"]["update"] == {
        "sessionUpdate": "usage_update",
        "used": 5,
        "size": 10,
    }

    turn_end = to_updates({"type": "turn_end", "data": {"stopReason": "end_turn"}})
    assert turn_end[0]["params"]["update"]["sessionUpdate"] == "session_info_update"
    assert turn_end[1] == {"stopReason": "end_turn"}

    assert to_updates({"type": "ping", "data": {}}) == []
