"""Agent 主循环的流拼装、兜底与工具链完整性（SPEC-001）。"""

from __future__ import annotations

import copy
import threading
from types import SimpleNamespace

import pytest

from src.agent.agent import Agent
from tests.support.fakes import FakeModel, chunk, completion, delta, tool_delta


class StreamHost:
    """只实现被测方法所需的最小宿主接口，避免构造整个 Agent。"""

    def __init__(self, model, interaction_id: int = 7) -> None:
        self.model = model
        self._interaction_id = interaction_id
        self._live_reasoning = ""
        self._tool_interrupt_event = threading.Event()
        self.phases: list[str] = []

    def _get_current_interaction_id(self) -> int:
        return self._interaction_id

    def _set_live_phase(self, phase: str) -> None:
        self.phases.append(phase)

    def _consume_stream(self, messages, tools, interaction_id):
        return Agent._consume_stream(self, messages, tools, interaction_id)


def test_consume_stream_assembles_content_reasoning_and_split_tool_arguments():
    model = FakeModel(
        stream_chunks=[
            chunk(
                delta=delta(
                    reasoning="先想",
                    tool_calls=[
                        tool_delta(
                            0,
                            call_id="call_1",
                            type="function",
                            name="read_",
                            arguments='{"path":',
                        )
                    ],
                )
            ),
            chunk(
                delta=delta(
                    content="你",
                    reasoning="一下",
                    tool_calls=[tool_delta(0, name="file", arguments=' "a.txt"}')],
                )
            ),
            chunk(delta=delta(content="好")),
            chunk(usage=SimpleNamespace(total_tokens=42)),
        ]
    )
    host = StreamHost(model)

    message, usage = Agent._consume_stream(host, [], None, host._interaction_id)

    assert message.content == "你好"
    assert message.reasoning_content == "先想一下"
    assert len(message.tool_calls) == 1
    assert message.tool_calls[0].id == "call_1"
    assert message.tool_calls[0].function.name == "read_file"
    assert message.tool_calls[0].function.arguments == '{"path": "a.txt"}'
    assert usage.total_tokens == 42
    # 思考增量只做实时透出，流结束后清空，避免污染下一轮
    assert host._live_reasoning == ""


def test_consume_stream_sorts_interleaved_tool_calls_by_index():
    model = FakeModel(
        stream_chunks=[
            chunk(
                delta=delta(
                    tool_calls=[
                        tool_delta(1, call_id="call_b", name="b", arguments="{}")
                    ]
                )
            ),
            chunk(
                delta=delta(
                    tool_calls=[
                        tool_delta(0, call_id="call_a", name="a", arguments="{}")
                    ]
                )
            ),
        ]
    )
    host = StreamHost(model)

    message, _ = Agent._consume_stream(host, [], None, host._interaction_id)

    assert [call.id for call in message.tool_calls] == ["call_a", "call_b"]


def test_stream_failure_falls_back_to_non_stream_once():
    model = FakeModel(
        fail_first_stream=True, response=completion(content="兜底", usage_tokens=9)
    )
    host = StreamHost(model)

    message, usage = Agent._chat_stream(host, [], None, host._interaction_id)

    assert message.content == "兜底"
    assert usage.total_tokens == 9
    assert host.phases == ["thinking"]
    assert [call["stream"] for call in model.calls] == [True, False]


def test_interrupt_is_not_retried_with_non_stream():
    model = FakeModel(error=InterruptedError("用户打断"))
    host = StreamHost(model)

    with pytest.raises(InterruptedError):
        Agent._chat_stream(host, [], None, host._interaction_id)

    assert len(model.calls) == 1


def _repair(history: list[dict]) -> list[dict]:
    host = SimpleNamespace(
        current_history=history,
        _history_lock=threading.RLock(),
    )
    Agent._check_and_fix_toolchain(host)
    return history


def _assistant(content: str | None, *call_ids: str) -> dict:
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


def _tool(call_id: str) -> dict:
    return {"role": "tool", "tool_call_id": call_id, "content": "ok"}


def test_complete_toolchain_is_left_untouched():
    history = [
        {"role": "user", "content": "hi"},
        _assistant(None, "a", "b"),
        _tool("a"),
        _tool("b"),
    ]
    snapshot = copy.deepcopy(history)

    assert _repair(history) == snapshot


def test_dangling_toolchain_keeps_text_and_drops_tool_calls():
    history = [
        {"role": "user", "content": "hi"},
        _assistant("我先看看", "a", "b"),
        _tool("a"),
        {"role": "system", "content": "workflow_hint"},
    ]

    _repair(history)

    assert history == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "我先看看"},
    ]


def test_dangling_toolchain_without_text_is_removed_entirely():
    history = [
        {"role": "user", "content": "hi"},
        _assistant("", "a"),
    ]

    _repair(history)

    assert history == [{"role": "user", "content": "hi"}]


def test_extra_tool_responses_also_trigger_cleanup():
    history = [
        {"role": "user", "content": "hi"},
        _assistant(None, "a"),
        _tool("a"),
        _tool("b"),
    ]

    _repair(history)

    assert history == [{"role": "user", "content": "hi"}]


def test_history_without_tool_calls_is_untouched():
    history = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "done"},
    ]
    snapshot = copy.deepcopy(history)

    assert _repair(history) == snapshot
