"""工具调用的解析、排序与系统参数注入（不依赖 Agent 实例）。"""

from __future__ import annotations

import json
from typing import Any, Iterable

from json_repair import repair_json

PARAM_DAMAGED_MESSAGE = "[Error] 系统拦截：工具参数格式严重损坏。"


def parse_arguments(arguments_str: str | None) -> dict | None:
    """解析模型给出的工具参数；无法恢复成 dict 时返回 None。"""
    if not arguments_str:
        return {}
    try:
        arguments = json.loads(arguments_str)
    except Exception:
        arguments = (
            repair_json(arguments_str, return_objects=True) if repair_json else {}
        )

    if not isinstance(arguments, dict):
        return None
    return arguments


def is_snapshot_dispatch_tool(tool_call: Any) -> bool:
    """识别「快照主历史并派发子代理」的工具（BrainStorm create）。"""
    if tool_call.function.name != "BrainStorm":
        return False
    try:
        args = (
            json.loads(tool_call.function.arguments)
            if tool_call.function.arguments
            else {}
        )
    except Exception:
        return False
    return isinstance(args, dict) and args.get("action") == "create"


def order_for_execution(tool_calls: list[Any]) -> list[Any]:
    """快照派发类工具延后到批次末尾，保证子代理快照兜住同批工具结果。"""
    if len(tool_calls) <= 1:
        return list(tool_calls)
    deferred = [tc for tc in tool_calls if is_snapshot_dispatch_tool(tc)]
    if not deferred:
        return list(tool_calls)
    others = [tc for tc in tool_calls if not is_snapshot_dispatch_tool(tc)]
    return others + deferred


def build_assistant_message(msg_resp: Any) -> dict:
    """把模型回复转成历史里的 assistant 消息（含 reasoning_content 与 tool_calls）。"""
    message = {"role": "assistant", "content": msg_resp.content or ""}

    rc = getattr(msg_resp, "reasoning_content", None)
    if rc is None and hasattr(msg_resp, "model_dump"):
        rc = msg_resp.model_dump().get("reasoning_content")
    if rc is not None:
        message["reasoning_content"] = rc

    if msg_resp.tool_calls:
        message["tool_calls"] = [
            {
                "id": t.id,
                "type": t.type,
                "function": {
                    "name": t.function.name,
                    "arguments": t.function.arguments,
                },
            }
            for t in msg_resp.tool_calls
        ]
    return message


def record_tool_usage(
    tool_calls: Iterable[Any] | None, used_tools: dict[str, list[dict]]
) -> dict[str, list[dict]]:
    """把本次工具调用记入累计表，并返回「本批」的调用表。"""
    current_tools: dict[str, list[dict]] = {}
    for call in tool_calls or []:
        arguments = {}
        if call.function.arguments:
            try:
                arguments = json.loads(call.function.arguments)
            except Exception:
                pass
        used_tools.setdefault(call.function.name, []).append(arguments)
        current_tools.setdefault(call.function.name, []).append(arguments)
    return current_tools


def with_system_arguments(
    tool_name: str,
    arguments: dict,
    *,
    session_id: str,
    tool_call_id: str | None = None,
    vision: bool = False,
    request_bytes: int | None = None,
    request_limit_bytes: int | None = None,
) -> dict:
    """按工具类型补齐模型不可见的系统参数；返回新字典，避免外部共享引用。"""
    prepared = dict(arguments)
    if tool_name == "Bash":
        prepared["session_id"] = session_id
    if tool_name == "Task" and vision:
        prepared["_session_id"] = session_id
        prepared["_request_bytes"] = request_bytes
        prepared["_request_limit_bytes"] = request_limit_bytes
    if tool_name == "BrainStorm":
        prepared["_tool_call_id"] = tool_call_id
    return prepared
