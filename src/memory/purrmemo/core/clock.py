"""记忆子系统共享的时间原语（SPEC-012）。"""

from __future__ import annotations

from datetime import datetime, timedelta


def now_iso() -> str:
    """当前本地时间的 ISO 字符串。"""
    return datetime.now().isoformat()


def parse_iso(value: str) -> datetime:
    """解析 ISO 时间字符串；格式非法时由调用方处理异常。"""
    return datetime.fromisoformat(value)


def days_since(value: str, now: datetime | None = None) -> int:
    """返回 ``value`` 距 ``now`` 的整天数。"""
    current = now or datetime.now()
    return (current - parse_iso(value)).days


def iso_days_ago(days: int, now: datetime | None = None) -> str:
    """返回 ``days`` 天前的 ISO 字符串。"""
    current = now or datetime.now()
    return (current - timedelta(days=days)).isoformat()
