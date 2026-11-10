"""模型对 Agent 暴露的最小能力契约（依赖倒置的接缝）。"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ChatModel(Protocol):
    """Agent 主循环所需的模型能力。

    ``vision`` 属于可选能力，Agent 用 ``getattr(model, "vision", False)``
    读取，因此不列入必需契约，测试替身无需实现。
    """

    def chat(
        self,
        messages: list,
        tools: list | None = None,
        cancel_event: Any = None,
        **kwargs: Any,
    ) -> Any:
        """发起对话；``stream=True`` 时返回可迭代的增量分片。"""
        ...

    def bind_task(self, task_id: str, task_name: str | None = None) -> "ChatModel":
        """绑定任务标识，供日志与用量追踪使用。"""
        ...

    def unbind(self) -> None:
        """释放占用的资源（如 API Key）。"""
        ...
