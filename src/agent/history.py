"""历史消息的结构化操作。

这里只放不依赖 Agent 实例的纯逻辑，Agent 只负责加锁与落盘。
"""

from __future__ import annotations

import datetime
import json
from dataclasses import dataclass

TIME_FORMAT = "%m-%d %H:%M:%S"


def workflow_hint(content: str) -> dict:
    """系统注入的 workflow_hint 消息（role=user，不算真人输入）。"""
    return {
        "role": "user",
        "content": json.dumps(
            {"type": "workflow_hint", "content": content}, ensure_ascii=False
        ),
    }


def system_event(content: str, now: datetime.datetime | None = None) -> dict:
    """构造 type=system 的 user 事件（记忆压缩/总结等系统提示共用）。"""
    moment = now or datetime.datetime.now()
    return {
        "role": "user",
        "content": json.dumps(
            {
                "events": [
                    {
                        "type": "system",
                        "time": moment.strftime(TIME_FORMAT),
                        "content": content,
                    }
                ]
            },
            ensure_ascii=False,
        ),
    }


def strip_reasoning(history: list[dict]) -> None:
    """清空历史里的思维链，只保留最终回复。"""
    for msg in history:
        if msg.get("role") == "assistant" and "reasoning_content" in msg:
            msg["reasoning_content"] = ""


@dataclass(frozen=True)
class ToolchainRepair:
    """一次工具链修复的统计信息，供调用方决定是否打日志。"""

    requested: int
    answered: int
    missing: int
    extra: int


def repair_toolchain(history: list[dict]) -> ToolchainRepair | None:
    """修复最后一条 assistant.tool_calls 与 tool 响应不匹配的断裂链。

    返回 None 表示无需修复；返回统计信息表示已就地清理。
    """
    if not history:
        return None

    assistant_idx = -1
    for i in range(len(history) - 1, -1, -1):
        msg = history[i]
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            assistant_idx = i
            break
    if assistant_idx < 0:
        return None

    assistant_msg = history[assistant_idx]
    requested_ids = {tc["id"] for tc in assistant_msg["tool_calls"]}
    answered_ids = {
        msg["tool_call_id"]
        for msg in history[assistant_idx + 1 :]
        if msg.get("role") == "tool" and msg.get("tool_call_id")
    }
    if requested_ids == answered_ids:
        return None

    repair = ToolchainRepair(
        requested=len(requested_ids),
        answered=len(answered_ids),
        missing=len(requested_ids - answered_ids),
        extra=len(answered_ids - requested_ids),
    )

    # 弹出这条 assistant 之后的所有消息
    del history[assistant_idx + 1 :]

    # 有实质文本则保留文本、只摘除 tool_calls；否则整条移除
    if assistant_msg.get("content") and str(assistant_msg.get("content")).strip():
        del assistant_msg["tool_calls"]
    else:
        history.pop()

    return repair
