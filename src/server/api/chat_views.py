"""会话与聊天的纯视图逻辑：列表/状态归一化、token 用量 payload。

路由层只负责读取 Agent/SessionStore，再由这里做裁剪与序列化。
"""

from __future__ import annotations


def build_session_list(sessions_dict: dict) -> list:
    """把会话索引归一化为前端列表，按 updated_at 倒序。"""
    sess_list = []
    for sid, info in sessions_dict.items():
        sess_list.append(
            {
                "id": sid,
                "alias": info.get("alias", sid),
                "messages_count": info.get("messages_count", 0),
                "updated_at": info.get("updated_at", ""),
                "project_id": info.get("project_id", ""),
            }
        )
    sess_list.sort(key=lambda x: str(x.get("updated_at") or ""), reverse=True)
    return sess_list


def build_session_status(status: dict, session_id: str) -> dict:
    """把全局 Agent 状态裁剪为单会话轮询结果（非当前会话一律视为 idle）。"""
    if status.get("session_id") != session_id:
        return {
            "is_thinking": False,
            "state": "idle",
            "compressing": status.get("compressing", False),
            "live_reasoning": "",
            "phase": "idle",
        }
    state = status.get("state", "idle")
    is_thinking = state != "idle"
    # aborting = 已打断但旧交互还在 unwind（模型调用退出/工具终止中）
    if state == "aborting":
        phase = "aborting"
    else:
        phase = status.get("live_phase", "idle") if is_thinking else "idle"
    return {
        "is_thinking": is_thinking,
        "state": state,
        "compressing": status.get("compressing", False),
        # 思考期间透出流式思考内容，思考结束（idle）自动清空
        "live_reasoning": status.get("live_reasoning", "") if is_thinking else "",
        # thinking=模型推理中 / processing=工具执行中 / aborting=打断等待收尾 / idle=空闲
        "phase": phase,
    }


def apply_buffer_to_events(events: list, buffer_fn) -> list:
    """对批量事件逐条做长文本占位替换，返回替换后的新列表。"""
    processed_events = []
    for event in events:
        event_type = event.get("type", "user")
        event_content = event.get("content", "")
        event_content = buffer_fn(event_content, event_type)
        processed_events.append({**event, "content": event_content})
    return processed_events


def build_token_status(
    session_id,
    agent,
    *,
    max_token: int,
    live_window_token,
    stored_window_token,
    stored_consumed,
) -> dict:
    """组装 token 进度 payload。

    传入的 session_id 不是 Agent 当前会话时取该会话落盘用量；正好是当前会话
    （或未指定会话）时取内存实时值，子代理累计始终取落盘聚合值。
    live_window_token / stored_window_token / stored_consumed 均为可调用对象，
    避免非活跃会话分支触发不必要的内存读取。
    """
    if session_id and (agent is None or agent.session_id != session_id):
        consumed = stored_consumed(session_id)
        return {
            "window_token": stored_window_token(session_id),
            "max_token": max_token,
            "consumed_main": consumed["main"],
            "consumed_sub": consumed["sub"],
            "consumed_total": consumed["total"],
        }

    consumed_main = agent.consumed_tokens if agent is not None else 0
    consumed_sub = stored_consumed(agent.session_id)["sub"] if agent is not None else 0
    return {
        "window_token": live_window_token(),
        "max_token": max_token,
        "consumed_main": consumed_main,
        "consumed_sub": consumed_sub,
        "consumed_total": consumed_main + consumed_sub,
    }
