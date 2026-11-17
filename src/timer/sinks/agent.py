"""投递给主 Agent；忙时延后重试。"""

from __future__ import annotations

from src.timer.models import Signal, TimerEvent


async def agent_sink(event: TimerEvent) -> Signal:
    from src.agent.heartbeat import heartbeat_content
    from src.agent.manager import manager

    agent = getattr(manager, "_agent", None)
    if agent is None or getattr(agent, "state", "idle") != "idle":
        return Signal("defer", defer=30.0)

    effect = event.effect or {}
    if effect.get("signal") == "heartbeat":
        content = heartbeat_content()
    else:
        payload = effect.get("payload") or {}
        content = payload.get("content") or payload.get("title") or ""
    if not content:
        return Signal("done")
    manager.agent_force_push(content=content, type="system_clock")
    return Signal("done")
