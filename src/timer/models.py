"""定时任务中心的数据模型与重复规则（SPEC-034）。"""

from __future__ import annotations

import math
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

CATCH_UP_MODES = ("skip", "once")
SIGNAL_ACTIONS = ("done", "defer", "skip")


@dataclass
class Signal:
    """接收方对一次到点事件的回应。"""

    action: str = "done"
    defer: float = 0.0
    data: dict = field(default_factory=dict)


@dataclass
class TimerEvent:
    """一条待执行的定时事件。"""

    id: str
    source: str
    target: str
    at: float
    effect: dict = field(default_factory=dict)
    repeat: dict | None = None
    catch_up: str = "skip"
    dedupe_key: str | None = None
    status: str = "pending"
    created_at: float = field(default_factory=time.time)
    last_fired_at: float | None = None
    finished_at: float | None = None
    # 接收方最近一次回执：{"action", "data", "at", "attempt"}
    result: dict | None = None
    # 仅运行时使用：cancel / replace 后到达的旧 sink 结果据此丢弃
    generation: int = field(default=0, compare=False)

    def __post_init__(self) -> None:
        self.at = float(self.at)
        self.id = str(self.id)
        self.source = str(self.source)
        self.target = str(self.target)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source": self.source,
            "target": self.target,
            "at": self.at,
            "effect": self.effect,
            "repeat": self.repeat,
            "catch_up": self.catch_up,
            "dedupe_key": self.dedupe_key,
            "status": self.status,
            "created_at": self.created_at,
            "last_fired_at": self.last_fired_at,
            "finished_at": self.finished_at,
            "result": self.result,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TimerEvent":
        if not isinstance(data, dict):
            raise ValueError("timer event must be an object")
        return cls(
            id=str(data.get("id") or uuid.uuid4().hex),
            source=str(data.get("source") or ""),
            target=str(data.get("target") or ""),
            at=float(data.get("at") or 0),
            effect=data.get("effect") if isinstance(data.get("effect"), dict) else {},
            repeat=data.get("repeat") if isinstance(data.get("repeat"), dict) else None,
            catch_up=str(data.get("catch_up") or "skip"),
            dedupe_key=data.get("dedupe_key"),
            status=str(data.get("status") or "pending"),
            created_at=float(data.get("created_at") or time.time()),
            last_fired_at=data.get("last_fired_at"),
            finished_at=data.get("finished_at"),
            result=data.get("result") if isinstance(data.get("result"), dict) else None,
        )


def next_after(event: TimerEvent, now: float) -> float | None:
    """计算重复事件的下一次触发时刻；无重复规则返回 None。"""
    repeat = event.repeat
    if not repeat:
        return None
    kind = repeat.get("kind")
    if kind == "interval":
        try:
            step = float(repeat.get("seconds") or 0)
        except (TypeError, ValueError):
            return None
        if step <= 0:
            return None
        if event.at > now:
            return event.at
        steps = math.floor((now - event.at) / step) + 1
        return event.at + steps * step
    if kind == "daily":
        return _next_daily(repeat.get("time"), now)
    return None


def _next_daily(value, now: float) -> float | None:
    try:
        hour, minute = (int(part) for part in str(value).split(":"))
    except (TypeError, ValueError):
        return None
    if not (0 <= hour < 24 and 0 <= minute < 60):
        return None
    current = datetime.fromtimestamp(now)
    candidate = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate.timestamp() <= now:
        candidate += timedelta(days=1)
    return candidate.timestamp()


def resolve_catch_up(event: TimerEvent, now: float, grace: float = 120.0) -> str:
    """重启后决定错过的事件怎么处理：wait / fire / advance / expire。"""
    if event.at >= now:
        return "wait"
    if event.catch_up == "once" and now - event.at <= grace:
        return "fire"
    if event.repeat:
        return "advance"
    return "expire"
