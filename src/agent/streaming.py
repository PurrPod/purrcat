"""流式响应的纯拼装逻辑：分片累积 → 与非流式等价的 message。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any


def _reasoning_of(delta: Any) -> str | None:
    """兼容不同 SDK：优先属性，其次 model_dump 里的 reasoning_content。"""
    rc = getattr(delta, "reasoning_content", None)
    if rc is None and hasattr(delta, "model_dump"):
        try:
            rc = delta.model_dump().get("reasoning_content")
        except Exception:
            rc = None
    return rc


class StreamAssembler:
    """把 OpenAI 兼容的流式分片累积成一条完整回复。"""

    def __init__(self) -> None:
        self._reasoning_parts: list[str] = []
        self._content_parts: list[str] = []
        self._tool_acc: dict[int, dict] = {}
        self.usage = None

    @property
    def reasoning_text(self) -> str:
        return "".join(self._reasoning_parts)

    def add(self, chunk: Any) -> None:
        if getattr(chunk, "usage", None):
            self.usage = chunk.usage
        if not getattr(chunk, "choices", None):
            return
        delta = chunk.choices[0].delta
        if delta is None:
            return

        rc = _reasoning_of(delta)
        if rc:
            self._reasoning_parts.append(rc)
        if delta.content:
            self._content_parts.append(delta.content)

        for tc in getattr(delta, "tool_calls", None) or []:
            slot = self._tool_acc.setdefault(
                tc.index,
                {"id": "", "type": "function", "name": "", "arguments": ""},
            )
            if tc.id:
                slot["id"] = tc.id
            if tc.type:
                slot["type"] = tc.type
            if tc.function:
                if tc.function.name:
                    slot["name"] += tc.function.name
                if tc.function.arguments:
                    slot["arguments"] += tc.function.arguments

    def build(self):
        tool_calls = [
            SimpleNamespace(
                id=slot["id"],
                type=slot["type"],
                function=SimpleNamespace(
                    name=slot["name"], arguments=slot["arguments"]
                ),
            )
            for _, slot in sorted(self._tool_acc.items())
        ] or None

        message = SimpleNamespace(
            content="".join(self._content_parts), tool_calls=tool_calls
        )
        reasoning_text = self.reasoning_text
        if reasoning_text:
            message.reasoning_content = reasoning_text
        return message
