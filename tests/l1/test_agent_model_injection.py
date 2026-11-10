"""Agent 支持注入模型，不注入时保持原行为（SPEC-002）。"""

from __future__ import annotations

import pytest

from src.agent import agent as agent_module
from src.agent.agent import Agent
from tests.support.fakes import FakeModel

HISTORY = [{"role": "system", "content": "stub system prompt"}]


class _StubStore:
    @staticmethod
    def load_global_memo():
        return []


class _StubTracker:
    def add(self, message):
        pass


class _StubHookHandler:
    def __init__(self, paradigm_path=None):
        self.paradigm_path = paradigm_path

    def execute(self, *args, **kwargs):
        return []

    def get_state(self):
        return {}

    def load_state(self, state):
        pass


class _BoomAgentModel:
    def __init__(self, *args, **kwargs):
        raise AssertionError("注入模型时不应构造 AgentModel")


@pytest.fixture
def agent_env(monkeypatch):
    """隔离 Agent 构造期的外部依赖，保证 L1 不读写真实 ~/.purrcat。"""
    monkeypatch.setattr(agent_module, "SessionStore", _StubStore)
    monkeypatch.setattr(agent_module, "Tracker", _StubTracker)
    monkeypatch.setattr(agent_module, "HookHandler", _StubHookHandler)
    monkeypatch.setattr(agent_module, "get_agent_model", lambda: "stub-model")
    monkeypatch.setattr(agent_module, "AgentModel", _BoomAgentModel)


def test_injected_model_is_used_and_bound_to_task(agent_env):
    model = FakeModel()

    agent = Agent(session_id="s-inject", initial_history=HISTORY, model=model)

    assert agent.model is model
    assert model.bind_task_calls == [("s-inject", "AgentMain")]


def test_stop_releases_injected_model(agent_env):
    model = FakeModel()
    agent = Agent(session_id="s-inject", initial_history=HISTORY, model=model)

    agent.stop()

    assert model.unbound is True


def test_agent_model_is_created_when_nothing_injected(agent_env, monkeypatch):
    created = []

    class StubAgentModel(FakeModel):
        def __init__(self, session_id):
            super().__init__()
            created.append(session_id)

    monkeypatch.setattr(agent_module, "AgentModel", StubAgentModel)

    agent = Agent(session_id="s-default", initial_history=HISTORY)

    assert created == ["s-default"]
    assert isinstance(agent.model, StubAgentModel)
