"""Agent 单个 epoch 的调用顺序（SPEC-018）。

用 Fake 模型/Hook 记录事件序列，锁住「epoch → 模型 → assistant 落盘 →
工具/钩子 → on_loop_end → 打回」的既有顺序，防止拆分时重排调用。
"""

from __future__ import annotations

import json

from src.agent import agent as agent_module
from src.agent.agent import Agent
from tests.support.fakes import chunk, delta, tool_delta


class _NoopTracker:
    def add(self, message):
        pass


class _RecordingModel:
    def __init__(self, events, responses):
        self.events = events
        self.responses = list(responses)
        self.vision = False
        self.calls = []

    def bind_task(self, task_id, task_name=None):
        return self

    def unbind(self):
        pass

    def chat(self, messages, tools=None, cancel_event=None, stream=False, **kwargs):
        self.events.append("model:stream" if stream else "model:chat")
        self.calls.append({"stream": stream, "messages": messages})
        return iter(self.responses.pop(0)) if stream else self.responses.pop(0)


class _RecordingHooks:
    def __init__(self, events, loop_end_success=(True,)):
        self.events = events
        self.loop_end_success = list(loop_end_success)

    def execute(self, stage_name, **kwargs):
        self.events.append(stage_name)
        if stage_name != "on_loop_end":
            return []
        success = self.loop_end_success.pop(0) if self.loop_end_success else True
        return [{"success": success, "inject_prompt": ""}]

    def get_state(self):
        return {}

    def load_state(self, state):
        pass


def _agent(model, hooks, events):
    agent = Agent(
        session_id="s-order",
        initial_history=[{"role": "system", "content": "系统提示"}],
        name="test-model",
        save_callback=lambda: None,
        model=model,
        hook_handler=hooks,
        tracker=_NoopTracker(),
        memo=[],
    )
    agent._get_tool_schema = lambda: []
    agent._set_live_phase = lambda phase: events.append(f"phase:{phase}")
    agent._spawn_hint_search = lambda merged, task_id: events.append(
        "spawn_hint_search"
    )
    return agent


def test_plain_reply_keeps_epoch_order():
    events = []
    model = _RecordingModel(events, [[chunk(delta=delta(content="完成"))]])
    agent = _agent(model, _RecordingHooks(events), events)
    agent.force_push("你好", type="user")

    agent.process_message()

    assert events == [
        "on_loop_start",
        "spawn_hint_search",
        "on_loop_epoch",
        "on_input_received",
        "phase:thinking",
        "model:stream",
        "on_loop_end",
        "phase:idle",
    ]
    assert [m["role"] for m in agent.current_history] == [
        "system",
        "user",
        "assistant",
    ]
    assert agent.current_history[-1]["content"] == "完成"


def test_tool_batch_runs_after_assistant_is_persisted(monkeypatch):
    events = []
    tool_frame = chunk(
        delta=delta(
            tool_calls=[
                tool_delta(
                    0,
                    call_id="call_1",
                    type="function",
                    name="Bash",
                    arguments='{"cmd": "ls"}',
                )
            ]
        )
    )
    model = _RecordingModel(
        events,
        [[tool_frame], [chunk(delta=delta(content="收尾"))]],
    )
    agent = _agent(model, _RecordingHooks(events), events)
    dispatched = []

    def fake_dispatch(name, arguments, **kwargs):
        events.append(f"tool:{name}")
        dispatched.append((name, arguments))
        return json.dumps(
            {"content": "ok", "metadata": {"type": "text", "snip": ""}},
            ensure_ascii=False,
        )

    monkeypatch.setattr(agent_module, "dispatch_tool", fake_dispatch)
    agent.force_push("跑一下", type="user")

    agent.process_message()

    assert events == [
        "on_loop_start",
        "spawn_hint_search",
        "on_loop_epoch",
        "on_input_received",
        "phase:thinking",
        "model:stream",
        "phase:processing",
        "tool:Bash",
        "on_tool_calling",
        "on_loop_epoch",
        "phase:thinking",
        "model:stream",
        "on_loop_end",
        "phase:idle",
    ]
    assert [m["role"] for m in agent.current_history] == [
        "system",
        "user",
        "assistant",
        "tool",
        "assistant",
    ]
    assert agent.current_history[2]["tool_calls"][0]["id"] == "call_1"
    assert agent.current_history[3]["tool_call_id"] == "call_1"
    assert dispatched[0][1]["session_id"] == "s-order"


def test_loop_end_failure_injects_workflow_hint_then_retries():
    events = []
    model = _RecordingModel(
        events,
        [
            [chunk(delta=delta(content="第一次"))],
            [chunk(delta=delta(content="第二次"))],
        ],
    )
    hooks = _RecordingHooks(events, loop_end_success=[False, True])
    agent = _agent(model, hooks, events)
    agent.force_push("你好", type="user")

    agent.process_message()

    assert events.count("on_loop_epoch") == 2
    assert [m["role"] for m in agent.current_history] == [
        "system",
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    hint = json.loads(agent.current_history[3]["content"])
    assert hint == {
        "type": "workflow_hint",
        "content": "未满足结束循环条件，已自动打回",
    }
    assert events[-2:] == ["on_loop_end", "phase:idle"]
