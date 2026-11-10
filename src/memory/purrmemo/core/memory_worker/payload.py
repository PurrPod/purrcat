"""pending 记忆文件的纯数据解析（SPEC-012）。"""

from __future__ import annotations

from dataclasses import dataclass

from ..clock import now_iso


@dataclass(frozen=True)
class PendingPayload:
    """一条 pending 记忆文件的字段集合。"""

    timestamp: str
    cognition: list
    user_profile: list
    work_exp: list
    events: list


def parse_pending_payload(data: dict) -> PendingPayload:
    """把 pending JSON 字典转为结构化对象，缺失字段保持原默认值。"""
    return PendingPayload(
        timestamp=data.get("timestamp", now_iso()),
        cognition=data.get("cognition", []),
        user_profile=data.get("user_profile", []),
        work_exp=data.get("work_exp", []),
        events=data.get("events", []),
    )


def iter_event_records(events: list, default_timestamp: str):
    """逐条产出 ``(内容, 时间)``；兼容字符串与对象两种事件形态。"""
    for event in events:
        if isinstance(event, dict):
            yield event.get("event", ""), event.get("time", default_timestamp)
        else:
            yield event, default_timestamp
