"""Agent 主循环与工具执行顺序的特征测试（SPEC-006）。

只使用替身，不联网、不读写真实 ~/.purrcat。
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from src.agent import agent as agent_module
from src.agent.agent import Agent
from tests.support.fakes import FakeModel, chunk, delta


class _NoopTracker:
    def add(self, message):
        pass


class _RecordingHooks:
    def __init__(self):
        self.stages: list[str] = []

    def execute(self, stage_name, **kwargs):
        self.stages.append(stage_name)
        return []

    def get_state(self):
        return {}

    def load_state(self, state):
        pass


def _agent(model):
    save_calls = []
    agent = Agent(
        session_id="s-characterization",
        initial_history=[{"role": "system", "content": "系统提示"}],
        name="test-model",
        save_callback=lambda: save_calls.append(1),
        model=model,
        hook_handler=_RecordingHooks(),
        tracker=_NoopTracker(),
        memo=[],
    )
    agent._get_tool_schema = lambda: []
    return agent, save_calls


def test_process_message_keeps_message_order_and_finishes_turn():
    model = FakeModel(stream_chunks=[chunk(delta=delta(content="完成了"))])
    agent, save_calls = _agent(model)
    phases = []
    agent._set_live_phase = phases.append
    agent.force_push("系统事件", type="system")

    agent.process_message()

    roles = [m["role"] for m in agent.current_history]
    assert roles == ["system", "user", "assistant"]
    assert agent.current_history[2]["content"] == "完成了"
    batch_event = json.loads(agent.current_history[1]["content"])["events"][0]
    assert batch_event["type"] == "system"
    assert batch_event["content"] == "系统事件"
    assert agent.pending_force_push == []
    assert phases == ["thinking", "idle"]
    assert agent.state == "idle"
    # 每条消息落盘一次 + 收尾 checkpoint
    assert len(save_calls) == 3
    assert agent.hook_handler.stages[:2] == ["on_loop_epoch", "on_loop_end"]


def _tool_call(call_id, name, arguments="{}"):
    return SimpleNamespace(
        id=call_id,
        type="function",
        function=SimpleNamespace(name=name, arguments=arguments),
    )


def test_execute_tool_calls_defers_brainstorm_and_injects_system_arguments(monkeypatch):
    model = FakeModel()
    agent, _ = _agent(model)
    dispatched = []

    def fake_dispatch(name, arguments, **kwargs):
        dispatched.append((name, arguments))
        return json.dumps(
            {"content": f"done:{name}", "metadata": {"type": "text", "snip": ""}},
            ensure_ascii=False,
        )

    monkeypatch.setattr(agent_module, "dispatch_tool", fake_dispatch)

    calls = [
        _tool_call("bs-1", "BrainStorm", '{"action": "create"}'),
        _tool_call("bash-1", "Bash", '{"cmd": "ls"}'),
    ]

    assert agent._execute_tool_calls(calls) is False

    assert [name for name, _ in dispatched] == ["Bash", "BrainStorm"]
    assert dispatched[0][1]["session_id"] == "s-characterization"
    assert dispatched[1][1]["_tool_call_id"] == "bs-1"

    tool_messages = [m for m in agent.current_history if m["role"] == "tool"]
    assert [m["name"] for m in tool_messages] == ["Bash", "BrainStorm"]
    assert [m["tool_call_id"] for m in tool_messages] == ["bash-1", "bs-1"]


def test_damaged_tool_arguments_write_error_without_dispatch(monkeypatch):
    model = FakeModel()
    agent, _ = _agent(model)
    dispatched = []
    monkeypatch.setattr(
        agent_module, "dispatch_tool", lambda *a, **k: dispatched.append(a)
    )

    agent._execute_tool_calls([_tool_call("bad-1", "Bash", "[1, 2]")])

    assert dispatched == []
    assert agent.current_history[-1]["content"].startswith("[Error]")
