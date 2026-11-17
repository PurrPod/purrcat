"""触发 DAG 工作流。"""

from __future__ import annotations

import asyncio

from src.timer.models import Signal, TimerEvent


async def graph_sink(event: TimerEvent) -> Signal:
    from src.harness.process import Task

    graph_name = event.target.split(":", 1)[1]
    payload = (event.effect or {}).get("payload") or {}
    task = Task(
        task_name=payload.get("task_name") or f"timer-{event.id}",
        graph_name=graph_name,
        inputs=payload.get("inputs") or {},
    )
    asyncio.create_task(task.run())
    return Signal(
        "done",
        data={
            "graph": graph_name,
            "task_id": task.task_id,
            "task_name": task.task_name,
        },
    )
