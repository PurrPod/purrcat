"""模型接缝：ChatModel 协议与测试替身的一致性（SPEC-002）。"""

from src.model.facade.protocol import ChatModel
from tests.support.fakes import FakeModel


def test_chat_model_protocol_declares_agent_contract():
    for name in ("chat", "bind_task", "unbind"):
        assert hasattr(ChatModel, name)
    assert getattr(ChatModel, "_is_runtime_protocol", False), (
        "ChatModel 必须是 runtime_checkable，测试才能做结构校验"
    )


def test_fake_model_satisfies_chat_model_protocol():
    assert isinstance(FakeModel(), ChatModel)


def test_bind_task_returns_model_for_chaining():
    model = FakeModel()

    assert model.bind_task("task-1", "AgentMain") is model
    assert model.bind_task_calls == [("task-1", "AgentMain")]
