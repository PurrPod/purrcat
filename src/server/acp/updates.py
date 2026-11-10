"""内部事件信封 → ACP session/update 词汇（唯一实现）。"""

from __future__ import annotations

import datetime
import itertools
import json

from src.tool.utils.token_limit import count_tokens, truncate_to_tokens

from .tool_vocab import (
    UPDATE_TOKEN_LIMIT,
    tool_kind,
    tool_locations,
    tool_raw,
    tool_title,
    vision_text_parts,
)

_tool_call_counter = itertools.count(1)
_msg_counter = itertools.count(1)


def truncate_update(text) -> str:
    """update 内容按 token 上限截断（超限截断，不异常）"""
    if not text:
        return ""
    text = str(text)
    try:
        if count_tokens(text) <= UPDATE_TOKEN_LIMIT:
            return text
        return truncate_to_tokens(text, UPDATE_TOKEN_LIMIT)
    except Exception:
        return text[:8000]


def _upd(acp_sid: str, update: dict) -> dict:
    """组装一条 session/update 通知载荷"""
    return {
        "jsonrpc": "2.0",
        "method": "session/update",
        "params": {"sessionId": acp_sid, "update": update},
    }


def _text_update(kind: str, text, *, with_message_id: bool = False) -> dict:
    payload = {
        "sessionUpdate": kind,
        "content": {"type": "text", "text": truncate_update(text)},
    }
    if with_message_id:
        payload["messageId"] = f"msg_{next(_msg_counter)}"
    return _upd("", payload)


def _tool_call_updates(data: dict) -> list[dict]:
    name = data.get("name", "tool")
    args = data.get("arguments")
    raw_result = data.get("result", "")
    update = _upd

    if isinstance(raw_result, list):
        body = vision_text_parts(raw_result) or "[图片已注入对话]"
        raw_output = {"content": body, "metadata": {}}
        status = "completed"
    else:
        # 结果解包：dispatch_tool 统一封包 {"content": 正文, "metadata": {type, snip}}
        # → 编辑器看 content 本体（不带 JSON 噪音）；宽容兼容裸 error dict / 纯文本
        try:
            parsed = json.loads(raw_result) if raw_result else None
        except Exception:
            parsed = None
        if (
            isinstance(parsed, dict)
            and isinstance(parsed.get("metadata"), dict)
            and "content" in parsed
        ):
            raw_content = parsed.get("content")
            if isinstance(raw_content, list):
                # vision 直注结果（防御：调用方未净化的旁路）
                body = vision_text_parts(raw_content) or "[图片已注入对话]"
                parsed = dict(parsed)
                parsed["content"] = body
            else:
                body = str(raw_content or "")
            raw_output = parsed
            status = (
                "failed"
                if isinstance(parsed.get("metadata"), dict)
                and parsed["metadata"].get("type") == "error"
                else "completed"
            )
        elif isinstance(parsed, dict):
            body = raw_result
            raw_output = parsed
            status = "failed" if parsed.get("error") else "completed"
        else:
            body = str(raw_result or "")
            raw_output = None
            status = "completed"

    tcid = f"acp_{next(_tool_call_counter)}"
    call = {
        "sessionUpdate": "tool_call",
        "toolCallId": tcid,
        "title": tool_title(name, args),
        "kind": tool_kind(name, args),
        "status": "pending",
    }
    locations = tool_locations(name, args)
    if locations:
        call["locations"] = locations
    raw_input = tool_raw(args)
    if raw_input is not None:
        call["rawInput"] = raw_input

    completed = {
        "sessionUpdate": "tool_call_update",
        "toolCallId": tcid,
        "status": status,
        "content": [
            {
                "type": "content",
                "content": {"type": "text", "text": truncate_update(body)},
            }
        ],
    }
    if isinstance(raw_output, dict):
        completed["rawOutput"] = raw_output  # schema 类型为 object，仅 dict 形态透出

    return [
        update("", call),
        update(
            "",
            {
                "sessionUpdate": "tool_call_update",
                "toolCallId": tcid,
                "status": "in_progress",
            },
        ),
        update("", completed),
    ]


def to_updates(envelope: dict) -> list[dict]:
    """内部事件信封 → update 载荷列表（空列表 = 不透出）。

    规范词汇映射（v1 事件粒度）：
    - agent_message → agent_message_chunk（规范唯一正文词汇；每条完整消息
      一个唯一 messageId——规范 §Message IDs：id 变化即新消息边界）
    - agent_thought → agent_thought_chunk
    - user_message → user_message_chunk（session/load 回放专用）
    - tool_call    → tool_call(pending) + tool_call_update(in_progress)
                     + tool_call_update(completed/failed+content) 三段
    - usage        → usage_update（used=window_token，size=模型上限）
    - turn_end     → session_info_update(updatedAt) + 自定义终结信号
    """
    etype = envelope["type"]
    data = envelope.get("data", {})

    if etype == "agent_message":
        return [
            _text_update(
                "agent_message_chunk", data.get("text", ""), with_message_id=True
            )
        ]

    if etype == "agent_thought":
        return [_text_update("agent_thought_chunk", data.get("text", ""))]

    if etype == "user_message":
        return [
            _text_update(
                "user_message_chunk", data.get("text", ""), with_message_id=True
            )
        ]

    if etype == "tool_call":
        return _tool_call_updates(data)

    if etype == "usage":
        return [
            _upd(
                "",
                {
                    "sessionUpdate": "usage_update",
                    "used": data.get("used", 0),
                    "size": data.get("size", 0),
                },
            )
        ]

    if etype == "phase":
        # ACP 无直接对应；自定义事件透出，传输方可忽略
        return [{"phase": data.get("phase", "idle")}]

    if etype == "replay_done":
        # session/load 回放终结标记（SSE 侧据补 load 响应；stdio 桥同步天然有序）
        return [{"replayDone": True}]

    if etype == "turn_end":
        # 回应 prompt 前先同步会话元数据（规范：所有 update 必须先于 prompt 响应）
        return [
            _upd(
                "",
                {
                    "sessionUpdate": "session_info_update",
                    "updatedAt": datetime.datetime.now()
                    .astimezone()
                    .isoformat(timespec="seconds"),
                },
            ),
            {"stopReason": data.get("stopReason", "end_turn")},
        ]

    return []
