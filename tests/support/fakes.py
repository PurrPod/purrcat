"""测试替身：用可编排的流式分片替代真实模型，避免测试依赖网络与 API Key。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any


def delta(
    *,
    content: str | None = None,
    reasoning: str | None = None,
    tool_calls: list[Any] | None = None,
) -> SimpleNamespace:
    """构造 OpenAI ChatCompletionChunk 的 delta 等价物。"""
    return SimpleNamespace(
        content=content,
        reasoning_content=reasoning,
        tool_calls=tool_calls,
    )


def chunk(*, delta: Any = None, usage: Any = None) -> SimpleNamespace:
    """构造一个流式分片；不传 delta 时模拟只带 usage 的末帧。"""
    choices = [SimpleNamespace(delta=delta)] if delta is not None else []
    return SimpleNamespace(choices=choices, usage=usage)


def tool_delta(
    index: int,
    *,
    call_id: str | None = None,
    type: str | None = None,
    name: str | None = None,
    arguments: str | None = None,
) -> SimpleNamespace:
    """构造增量 tool_call 分片；name/arguments 可跨多个分片拼接。"""
    function = None
    if name is not None or arguments is not None:
        function = SimpleNamespace(name=name, arguments=arguments)
    return SimpleNamespace(index=index, id=call_id, type=type, function=function)


def completion(*, content: str = "", usage_tokens: int = 0) -> SimpleNamespace:
    """构造非流式 ChatCompletion 等价物，供兜底路径使用。"""
    message = SimpleNamespace(content=content, tool_calls=None)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message)],
        usage=SimpleNamespace(total_tokens=usage_tokens),
    )


class FakeModel:
    """按脚本返回流式分片或非流式响应，并记录调用参数。"""

    def __init__(
        self,
        *,
        stream_chunks: list[Any] | None = None,
        response: Any = None,
        fail_first_stream: bool = False,
        error: BaseException | None = None,
    ) -> None:
        self.stream_chunks = list(stream_chunks or [])
        self.response = response
        self.fail_first_stream = fail_first_stream
        self.error = error
        self.calls: list[dict[str, Any]] = []
        self.vision = False
        self.bind_task_calls: list[tuple[str, str | None]] = []
        self.unbound = False

    def bind_task(self, task_id: str, task_name: str | None = None) -> "FakeModel":
        self.bind_task_calls.append((task_id, task_name))
        return self

    def unbind(self) -> None:
        self.unbound = True

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[Any] | None = None,
        cancel_event: Any = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> Any:
        self.calls.append(
            {
                "stream": stream,
                "messages": messages,
                "tools": tools,
                "cancel_event": cancel_event,
            }
        )
        if stream:
            if self.error is not None:
                raise self.error
            if self.fail_first_stream:
                self.fail_first_stream = False
                raise RuntimeError("stream unavailable")
            return iter(self.stream_chunks)
        return self.response
