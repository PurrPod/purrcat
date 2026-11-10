"""记忆压缩的提示词、总结提取与历史重建（SPEC-006）。"""

from __future__ import annotations

import datetime
import json

import pytest
from types import SimpleNamespace

from src.agent.compression import (
    MAIN_SUMMARY_FALLBACK,
    compression_prompt,
    extract_memo_summary,
    find_safe_split_index,
    rebuild_main_history,
    rebuild_sub_history,
    run_summary_attempts,
)


def _memo_response(payload, content=""):
    message = SimpleNamespace(
        content=content,
        tool_calls=[
            SimpleNamespace(
                function=SimpleNamespace(
                    name="Memo", arguments=json.dumps(payload, ensure_ascii=False)
                )
            )
        ],
    )
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def test_extract_memo_summary_serializes_dict():
    text, valid = extract_memo_summary(
        _memo_response({"action": "add", "memo_data": {"a": 1}}).choices[0].message
    )

    assert valid is True
    assert json.loads(text) == {"a": 1}


def test_extract_memo_summary_requires_add_with_data():
    message = _memo_response({"action": "search", "memo_data": "x"}).choices[0].message

    assert extract_memo_summary(message) == (None, False)


def test_extract_memo_summary_ignores_other_tools_and_bad_json():
    other = SimpleNamespace(
        content="",
        tool_calls=[
            SimpleNamespace(function=SimpleNamespace(name="Bash", arguments="{}"))
        ],
    )
    broken = SimpleNamespace(
        content="",
        tool_calls=[
            SimpleNamespace(function=SimpleNamespace(name="Memo", arguments="{"))
        ],
    )

    assert extract_memo_summary(other) == (None, False)
    assert extract_memo_summary(broken) == (None, False)


def test_compression_prompt_is_system_event():
    message = compression_prompt("总结", now=datetime.datetime(2026, 1, 2, 3, 4, 5))

    event = json.loads(message["content"])["events"][0]
    assert event == {"type": "system", "time": "01-02 03:04:05", "content": "总结"}


def test_summary_attempts_stops_on_first_valid_memo():
    calls = []

    def chat(messages):
        calls.append(messages)
        return _memo_response({"action": "add", "memo_data": "总结"})

    messages = [{"role": "system", "content": "s"}]
    summary = run_summary_attempts(
        chat,
        messages,
        instruction="压缩",
        warning_text=lambda attempt: f"警告{attempt}",
        fallback_text=MAIN_SUMMARY_FALLBACK,
        warning_prefix="[Warn.Test]",
        error_prefix="[Error.Test]",
    )

    assert summary == "总结"
    assert len(calls) == 1
    assert len(messages) == 2


def test_summary_attempts_retries_with_warning_then_succeeds():
    attempts = []

    def chat(messages):
        attempts.append(len(messages))
        if len(attempts) == 1:
            return _memo_response({"action": "search", "memo_data": None})
        return _memo_response({"action": "add", "memo_data": "补上"})

    messages = []
    summary = run_summary_attempts(
        chat,
        messages,
        instruction="压缩",
        warning_text=lambda attempt: f"警告{attempt}",
        fallback_text=MAIN_SUMMARY_FALLBACK,
        warning_prefix="[Warn.Test]",
        error_prefix="[Error.Test]",
    )

    assert summary == "补上"
    assert len(attempts) == 2
    # 压缩指令 + 第一次失败后的警告
    assert len(messages) == 2


def test_summary_attempts_falls_back_to_response_content():
    def chat(messages):
        return _memo_response({"action": "search"}, content="模型直接给了总结")

    summary = run_summary_attempts(
        chat,
        [],
        instruction="压缩",
        warning_text=lambda attempt: "警告",
        fallback_text=MAIN_SUMMARY_FALLBACK,
        warning_prefix="[Warn.Test]",
        error_prefix="[Error.Test]",
        max_retries=1,
    )

    assert summary == "模型直接给了总结"


def test_summary_attempts_network_error_uses_fallback():
    def chat(messages):
        raise RuntimeError("网络断了")

    summary = run_summary_attempts(
        chat,
        [],
        instruction="压缩",
        warning_text=lambda attempt: "警告",
        fallback_text=MAIN_SUMMARY_FALLBACK,
        warning_prefix="[Warn.Test]",
        error_prefix="[Error.Test]",
    )

    assert summary == MAIN_SUMMARY_FALLBACK


def test_find_safe_split_index_moves_before_dangling_tool_messages():
    messages = [
        {"role": "system", "content": "s"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "a"}]},
        {"role": "tool", "tool_call_id": "a"},
    ] + [{"role": "user", "content": str(i)} for i in range(9)]

    # len=12, keep_recent=10 → split=2；但 2 是 tool，向前移到 1（assistant 带 tool_calls）
    assert find_safe_split_index(messages, keep_recent=10) == 1


def test_rebuild_main_history_keeps_only_system_and_summary():
    history = rebuild_main_history(
        "新系统提示", "总结内容", now=datetime.datetime(2026, 1, 2, 3, 4, 5)
    )

    assert [m["role"] for m in history] == ["system", "user"]
    assert history[0]["content"] == "新系统提示"
    summary_event = json.loads(history[1]["content"])["events"][0]
    assert summary_event["content"] == "【历史记忆总结】\n总结内容"


def test_rebuild_sub_history_keeps_recent_tail_and_clears_reasoning():
    messages = [{"role": "system", "content": "旧"}] + [
        {"role": "assistant", "content": str(i), "reasoning_content": "想"}
        for i in range(12)
    ]

    history = rebuild_sub_history(
        messages, "新系统", "总结", keep_recent=10, now=datetime.datetime(2026, 1, 2)
    )

    assert history[0] == {"role": "system", "content": "新系统"}
    assert [m["role"] for m in history[1:-1]] == ["assistant"] * 10
    assert all(m.get("reasoning_content") == "" for m in history[1:-1])
    summary_event = json.loads(history[-1]["content"])["events"][0]
    assert summary_event["content"] == "【历史记忆总结】\n总结"


@pytest.mark.parametrize("message_count", [0, 1, 9, 10])
def test_find_safe_split_index_never_returns_zero(message_count):
    messages = [{"role": "user", "content": str(i)} for i in range(message_count)]

    assert find_safe_split_index(messages) >= 1
