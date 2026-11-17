"""推送到 UI 订阅者（SSE）。"""

from __future__ import annotations

from src.timer.models import Signal, TimerEvent


async def ui_sink(event: TimerEvent) -> Signal:
    # 实际推送由 TimerService._publish 统一完成，这里只确认事件已送达。
    return Signal("done")
