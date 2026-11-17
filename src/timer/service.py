"""定时任务服务：唯一 asyncio 循环，按事件库计算下次唤醒时间（SPEC-034）。

线程侧（心跳、API）只做「改表 + 落盘 + 线程安全唤醒」，不直接 await。
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
import uuid

from src.timer.models import (
    CATCH_UP_MODES,
    Signal,
    TimerEvent,
    next_after,
    resolve_catch_up,
)
from src.timer.store import TimerStore
from src.utils.config import TIMER_FILE

logger = logging.getLogger(__name__)


def _default_sinks() -> dict:
    from src.timer.sinks import agent_sink, graph_sink, ui_sink

    return {"agent": agent_sink, "graph": graph_sink, "ui": ui_sink}


class TimerService:
    def __init__(
        self,
        store_path: str | None = None,
        sinks: dict | None = None,
        grace: float = 120.0,
    ) -> None:
        self._store = TimerStore(store_path or TIMER_FILE)
        self._lock = threading.RLock()
        self._wake = asyncio.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task | None = None
        self._dispatch_tasks: set[asyncio.Task] = set()
        self._subscribers: dict[int, tuple] = {}
        self._next_subscriber_id = 0
        self._grace = grace
        self._running = False
        self._stopped = False
        self._sinks = sinks if sinks is not None else _default_sinks()

    # ------------------------------------------------------------------ 生命周期

    async def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._loop = asyncio.get_running_loop()
            self._wake = asyncio.Event()
            self._stopped = False
            self._store.load()
            self._apply_catch_up(time.time())
            self._store.save()
            self._running = True
        self._task = asyncio.create_task(self._run(), name="purrcat-timer")

    async def stop(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._stopped = True
            self._running = False
        self._notify_wake()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        pending = [task for task in self._dispatch_tasks if not task.done()]
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        with self._lock:
            self._store.save()
            self._loop = None

    # ------------------------------------------------------------------ 事件变更

    def add_event(self, data: dict) -> TimerEvent:
        event = _build_event(data)
        with self._lock:
            self._store.upsert(event)
            self._store.save()
        self._notify_wake()
        return event

    def replace_source(self, source: str, events: list[dict]) -> list[TimerEvent]:
        if not source:
            raise ValueError("source is required")
        built = [_build_event({**event, "source": source}) for event in events]
        with self._lock:
            result = self._store.replace_source(source, built)
            self._store.save()
        self._notify_wake()
        return result

    def cancel(self, event_id: str) -> bool:
        with self._lock:
            removed = self._store.cancel(event_id)
            if removed:
                self._store.save()
        if removed:
            self._notify_wake()
        return removed

    def list_events(self, source: str | None = None) -> list[dict]:
        with self._lock:
            return [event.to_dict() for event in self._store.list(source)]

    def state(self) -> dict:
        with self._lock:
            data = self._store.state()
            data["running"] = self._running
            data["events"] = [
                event.to_dict() for event in self._store.list(include_finished=False)
            ]
            return data

    # ------------------------------------------------------------------ 订阅

    def subscribe(self, callback, loop: asyncio.AbstractEventLoop | None = None):
        with self._lock:
            self._next_subscriber_id += 1
            key = self._next_subscriber_id
            self._subscribers[key] = (callback, loop or self._loop)

        def unsubscribe() -> None:
            with self._lock:
                self._subscribers.pop(key, None)

        return unsubscribe

    # ------------------------------------------------------------------ 主循环

    async def _run(self) -> None:
        while True:
            with self._lock:
                if self._stopped:
                    return
                now = time.time()
                due = []
                while True:
                    event = self._store.pop_due(now)
                    if event is None:
                        break
                    due.append(event)
                for event in due:
                    task = asyncio.create_task(self._dispatch(event))
                    self._dispatch_tasks.add(task)
                    task.add_done_callback(self._dispatch_tasks.discard)
                self._wake.clear()
                next_at = self._store.next_at()
            if next_at is None:
                await self._wake.wait()
            else:
                timeout = max(0.0, next_at - time.time())
                try:
                    await asyncio.wait_for(self._wake.wait(), timeout=timeout)
                except asyncio.TimeoutError:
                    pass

    async def _dispatch(self, event: TimerEvent) -> None:
        sink = self._select_sink(event.target)
        if sink is None:
            signal = Signal("done", data={"error": f"unknown target: {event.target}"})
        else:
            try:
                signal = await sink(event)
            except Exception as exc:  # 接收方异常不应终止整个循环
                logger.exception("timer sink failed: %s", event.target)
                signal = Signal("defer", defer=30.0, data={"error": str(exc)})
        if not isinstance(signal, Signal):
            signal = Signal("done")
        with self._lock:
            stored, finished = self._store.finish_dispatch(
                event.id, event.generation, signal, time.time()
            )
            self._store.save()
        if stored is None:
            return
        # defer / repeat 会改变下次触发时刻，必须唤醒主循环重新计算 sleep。
        self._notify_wake()
        payload = {
            "type": "fired" if finished else "rescheduled",
            "event": stored.to_dict(),
            "signal": signal.action,
            "result": stored.result,
        }
        self._publish(payload)

    def _select_sink(self, target: str):
        if target in ("main", "agent"):
            return self._sinks.get("agent")
        if target.startswith("graph:"):
            return self._sinks.get("graph")
        if target.startswith("ui:"):
            return self._sinks.get("ui")
        return None

    def _apply_catch_up(self, now: float) -> None:
        for event in self._store.list(include_finished=False):
            decision = resolve_catch_up(event, now, self._grace)
            if decision == "fire":
                continue
            if decision == "advance":
                nxt = next_after(event, now)
                if nxt is None:
                    event.status = "done"
                    event.finished_at = now
                else:
                    event.at = nxt
            elif decision == "expire":
                event.status = "done"
                event.finished_at = now

    # ------------------------------------------------------------------ 工具

    def _notify_wake(self) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        try:
            loop.call_soon_threadsafe(self._wake.set)
        except RuntimeError:
            pass

    def _publish(self, payload: dict) -> None:
        with self._lock:
            subscribers = list(self._subscribers.values())
        for callback, loop in subscribers:
            target_loop = loop or self._loop
            if target_loop is None:
                try:
                    callback(payload)
                except Exception:
                    pass
                continue
            if target_loop.is_closed():
                continue
            try:
                target_loop.call_soon_threadsafe(callback, payload)
            except RuntimeError:
                pass


def _build_event(data: dict) -> TimerEvent:
    if not isinstance(data, dict):
        raise ValueError("timer event must be an object")
    source = str(data.get("source") or "").strip()
    target = str(data.get("target") or "").strip()
    if not source or not target:
        raise ValueError("source and target are required")
    if data.get("at") is None:
        raise ValueError("at is required")
    at = float(data["at"])
    catch_up = str(data.get("catch_up") or "skip")
    if catch_up not in CATCH_UP_MODES:
        raise ValueError(f"unsupported catch_up: {catch_up}")
    effect = data.get("effect") or {}
    if not isinstance(effect, dict):
        raise ValueError("effect must be an object")
    repeat = data.get("repeat")
    if repeat is not None and not isinstance(repeat, dict):
        raise ValueError("repeat must be an object or null")
    return TimerEvent(
        id=str(data.get("id") or uuid.uuid4().hex),
        source=source,
        target=target,
        at=at,
        effect=effect,
        repeat=repeat,
        catch_up=catch_up,
        dedupe_key=data.get("dedupe_key"),
    )


_service: TimerService | None = None
_service_lock = threading.Lock()


def get_timer_service() -> TimerService:
    global _service
    with _service_lock:
        if _service is None:
            _service = TimerService()
        return _service


def reset_timer_service() -> None:
    """测试或重启时丢弃单例（调用方负责先 stop）。"""
    global _service
    with _service_lock:
        _service = None
