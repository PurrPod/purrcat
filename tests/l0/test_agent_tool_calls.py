"""工具参数解析、执行排序与系统参数注入（SPEC-006）。"""

from __future__ import annotations

import json
from types import SimpleNamespace

from src.agent.tool_calls import (
    PARAM_DAMAGED_MESSAGE,
    build_assistant_message,
    is_snapshot_dispatch_tool,
    order_for_execution,
    parse_arguments,
    record_tool_usage,
    with_system_arguments,
)


def _call(call_id, name, arguments=""):
    return SimpleNamespace(
        id=call_id,
        type="function",
        function=SimpleNamespace(name=name, arguments=arguments),
    )


def test_parse_arguments_handles_empty_valid_and_damaged_json():
    assert parse_arguments(None) == {}
    assert parse_arguments("") == {}
    assert parse_arguments('{"a": 1}') == {"a": 1}
    assert parse_arguments('{"a": 1') == {"a": 1}
    assert parse_arguments("[1, 2]") is None
    assert PARAM_DAMAGED_MESSAGE.startswith("[Error]")


def test_is_snapshot_dispatch_tool_requires_create_action():
    assert is_snapshot_dispatch_tool(
        _call("1", "BrainStorm", json.dumps({"action": "create"}))
    )
    assert not is_snapshot_dispatch_tool(
        _call("1", "BrainStorm", json.dumps({"action": "cancel"}))
    )
    assert not is_snapshot_dispatch_tool(_call("1", "Bash", "{}"))
    assert not is_snapshot_dispatch_tool(_call("1", "BrainStorm", "{bad"))


def test_order_for_execution_defers_only_snapshot_dispatch():
    bash = _call("1", "Bash", "{}")
    bs = _call("2", "BrainStorm", '{"action": "create"}')
    memo = _call("3", "Memo", "{}")

    assert order_for_execution([bs, bash, memo]) == [bash, memo, bs]


def test_order_for_execution_preserves_original_when_not_needed():
    calls = [_call("1", "Bash", "{}"), _call("2", "Memo", "{}")]

    assert order_for_execution(calls) == calls
    assert order_for_execution([]) == []


def test_record_tool_usage_accumulates_and_returns_current_batch():
    used = {"Bash": [{"cmd": "old"}]}
    calls = [_call("1", "Bash", '{"cmd": "ls"}'), _call("2", "Bash", "{bad")]

    current = record_tool_usage(calls, used)

    assert used["Bash"] == [{"cmd": "old"}, {"cmd": "ls"}, {}]
    assert current == {"Bash": [{"cmd": "ls"}, {}]}


def test_with_system_arguments_injects_per_tool_fields_without_mutating_input():
    original = {"cmd": "ls"}

    bash = with_system_arguments("Bash", original, session_id="s1")
    other = with_system_arguments("Memo", original, session_id="s1")
    task = with_system_arguments(
        "Task",
        original,
        session_id="s1",
        vision=True,
        request_bytes=10,
        request_limit_bytes=20,
    )
    task_no_vision = with_system_arguments("Task", original, session_id="s1")
    brainstorm = with_system_arguments(
        "BrainStorm", original, session_id="s1", tool_call_id="call_9"
    )

    assert original == {"cmd": "ls"}
    assert bash == {"cmd": "ls", "session_id": "s1"}
    assert other == {"cmd": "ls"}
    assert task == {
        "cmd": "ls",
        "_session_id": "s1",
        "_request_bytes": 10,
        "_request_limit_bytes": 20,
    }
    assert task_no_vision == {"cmd": "ls"}
    assert brainstorm == {"cmd": "ls", "_tool_call_id": "call_9"}


def test_build_assistant_message_keeps_reasoning_and_tool_calls():
    response = SimpleNamespace(
        content=None,
        reasoning_content="思考",
        tool_calls=[_call("c1", "Bash", "{}")],
    )

    message = build_assistant_message(response)

    assert message["role"] == "assistant"
    assert message["content"] == ""
    assert message["reasoning_content"] == "思考"
    assert message["tool_calls"][0]["function"]["name"] == "Bash"


def test_build_assistant_message_uses_model_dump_fallback():
    class Response:
        content = "hi"
        tool_calls = None

        def model_dump(self):
            return {"reasoning_content": "兜底思考"}

    assert build_assistant_message(Response())["reasoning_content"] == "兜底思考"
