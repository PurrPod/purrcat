"""主/子 Agent 消息历史的纯函数（SPEC-006）。"""

from __future__ import annotations

import copy
import datetime
import json

from src.agent.history import (
    repair_toolchain,
    strip_reasoning,
    system_event,
    workflow_hint,
)


def test_workflow_hint_is_json_user_message():
    message = workflow_hint("继续")

    assert message["role"] == "user"
    assert json.loads(message["content"]) == {
        "type": "workflow_hint",
        "content": "继续",
    }


def test_system_event_uses_expected_time_format():
    now = datetime.datetime(2026, 1, 2, 3, 4, 5)

    message = system_event("提示", now=now)

    payload = json.loads(message["content"])
    assert payload["events"][0]["time"] == "01-02 03:04:05"
    assert payload["events"][0]["type"] == "system"


def test_strip_reasoning_only_touches_assistant():
    history = [
        {"role": "assistant", "content": "a", "reasoning_content": "想"},
        {"role": "user", "content": "u", "reasoning_content": "保留"},
    ]

    strip_reasoning(history)

    assert history[0]["reasoning_content"] == ""
    assert history[1]["reasoning_content"] == "保留"


def _assistant(content, *call_ids):
    return {
        "role": "assistant",
        "content": content,
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {"name": "tool", "arguments": "{}"},
            }
            for call_id in call_ids
        ],
    }


def test_repair_toolchain_reports_counts_for_dangling_chain():
    history = [
        {"role": "user", "content": "hi"},
        _assistant("先看看", "a", "b"),
        {"role": "tool", "tool_call_id": "a", "content": "ok"},
    ]

    repair = repair_toolchain(history)

    assert (repair.requested, repair.answered, repair.missing, repair.extra) == (
        2,
        1,
        1,
        0,
    )
    assert history == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "先看看"},
    ]


def test_repair_toolchain_leaves_complete_chain_untouched():
    history = [
        {"role": "user", "content": "hi"},
        _assistant(None, "a"),
        {"role": "tool", "tool_call_id": "a", "content": "ok"},
    ]
    snapshot = copy.deepcopy(history)

    assert repair_toolchain(history) is None
    assert history == snapshot
