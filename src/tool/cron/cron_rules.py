"""Cron 的时间、重复规则与展示文案纯函数。

与文件读写、工具动作分发解耦，便于直接验证边界。
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

VALID_REPEAT_RULES = (
    "none",
    "everyday",
    "weekly_1",
    "weekly_2",
    "weekly_3",
    "weekly_4",
    "weekly_5",
    "weekly_6",
    "weekly_7",
)

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def is_valid_trigger_time(value: str) -> bool:
    """严格 HH:MM 24 小时制。"""
    return bool(_TIME_RE.match(value or ""))


def is_valid_repeat_rule(rule: str) -> bool:
    return rule in VALID_REPEAT_RULES


def next_run_time(
    trigger_time: str, repeat_rule: str = "none", now: datetime | None = None
) -> datetime | None:
    """计算下一次触发时间；非法时间/规则返回 None。

    一次性与每天规则都取“今天该时刻，已过则明天”；weekly_N 取最近的
    对应星期几，今天已过则顺延一周。
    """
    if not is_valid_trigger_time(trigger_time) or not is_valid_repeat_rule(repeat_rule):
        return None

    current = now or datetime.now()
    hour, minute = (int(part) for part in trigger_time.split(":"))
    candidate = current.replace(hour=hour, minute=minute, second=0, microsecond=0)

    if repeat_rule in ("none", "everyday"):
        return candidate + timedelta(days=1) if candidate <= current else candidate

    weekday = int(repeat_rule.split("_")[1])
    candidate += timedelta(days=(weekday - candidate.isoweekday()) % 7)
    if candidate <= current:
        candidate += timedelta(days=7)
    return candidate


def format_cron_list(crons: list) -> str:
    """把 cron 记录拼成工具返回的平文本。"""
    return "\n".join(
        [
            f"- [{c.get('id')}] {c.get('title')} | 时间: {c.get('trigger_time')} | "
            f"重复: {c.get('repeat_rule')} | 激活: {c.get('active')}\n"
            f"  描述: {c.get('description', '')}"
            for c in crons
        ]
    )
