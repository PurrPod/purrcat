"""定时事件的落盘与内存索引（SPEC-034）。"""

from __future__ import annotations

import copy
import time

from src.timer.models import TimerEvent, next_after
from src.utils._fs import read_json, write_json_atomic

MAX_FINISHED = 200


class TimerStore:
    """同步事件表；调用方负责加锁与落盘时机。"""

    def __init__(self, path: str) -> None:
        self.path = path
        self._events: dict[str, TimerEvent] = {}
        self._dispatching: set[str] = set()

    def load(self) -> list[TimerEvent]:
        data = read_json(self.path, default={}) or {}
        raw_events = data.get("events") if isinstance(data, dict) else None
        for raw in raw_events or []:
            try:
                event = TimerEvent.from_dict(raw)
            except (TypeError, ValueError):
                continue
            if not event.source or not event.target:
                continue
            self._events[event.id] = event
        return list(self._events.values())

    def save(self) -> None:
        self._prune()
        write_json_atomic(
            self.path,
            {"version": 1, "events": [e.to_dict() for e in self._events.values()]},
        )

    def get(self, event_id: str) -> TimerEvent | None:
        return self._events.get(event_id)

    def upsert(self, event: TimerEvent) -> TimerEvent:
        """同 source + dedupe_key 的旧 pending 事件被覆盖。"""
        if event.dedupe_key:
            now = time.time()
            for existing in self._events.values():
                if (
                    existing.status == "pending"
                    and existing.id != event.id
                    and existing.source == event.source
                    and existing.dedupe_key == event.dedupe_key
                ):
                    existing.status = "cancelled"
                    existing.finished_at = now
                    self._dispatching.discard(existing.id)
        self._events[event.id] = event
        return event

    def cancel(self, event_id: str) -> bool:
        event = self._events.get(event_id)
        if event is None or event.status != "pending":
            return False
        event.status = "cancelled"
        event.finished_at = time.time()
        self._dispatching.discard(event_id)
        return True

    def replace_source(self, source: str, events: list[TimerEvent]) -> list[TimerEvent]:
        keep = {event.id for event in events}
        now = time.time()
        for existing in self._events.values():
            if (
                existing.source == source
                and existing.status == "pending"
                and existing.id not in keep
            ):
                existing.status = "cancelled"
                existing.finished_at = now
                self._dispatching.discard(existing.id)
        for event in events:
            self.upsert(event)
        return self.list(source=source, include_finished=False)

    def list(
        self, source: str | None = None, include_finished: bool = True
    ) -> list[TimerEvent]:
        events = [
            event
            for event in self._events.values()
            if (source is None or event.source == source)
            and (include_finished or event.status == "pending")
        ]
        return sorted(events, key=lambda event: (event.at, event.created_at))

    def pop_due(self, now: float) -> TimerEvent | None:
        """取出最早到期事件并标记为 dispatching，返回事件快照。"""
        due = [
            event
            for event in self._events.values()
            if event.status == "pending"
            and event.id not in self._dispatching
            and event.at <= now
        ]
        if not due:
            return None
        event = min(due, key=lambda item: (item.at, item.created_at))
        self._dispatching.add(event.id)
        event.generation += 1
        return copy.deepcopy(event)

    def finish_dispatch(self, event_id: str, generation: int, signal, now: float):
        """回写到点结果；返回 (event, 是否进入终态)。"""
        event = self._events.get(event_id)
        if event is None or event.status != "pending" or event.generation != generation:
            self._dispatching.discard(event_id)
            return event, False
        self._dispatching.discard(event_id)
        action = getattr(signal, "action", "done")
        event.result = {
            "action": action,
            "data": getattr(signal, "data", {}) or {},
            "at": now,
            "attempt": event.generation,
        }
        if action == "defer":
            delay = max(0.05, float(getattr(signal, "defer", 0) or 0))
            event.at = now + delay
            return event, False
        event.last_fired_at = now
        if action != "done":
            event.status = "cancelled"
            event.finished_at = now
            return event, True
        nxt = next_after(event, now)
        if nxt is None:
            event.status = "done"
            event.finished_at = now
            return event, True
        event.at = nxt
        return event, False

    def next_at(self) -> float | None:
        ats = [
            event.at
            for event in self._events.values()
            if event.status == "pending" and event.id not in self._dispatching
        ]
        return min(ats) if ats else None

    def state(self) -> dict:
        counts = {"pending": 0, "done": 0, "cancelled": 0}
        for event in self._events.values():
            if event.status in counts:
                counts[event.status] += 1
        return {
            "pending": counts["pending"],
            "counts": counts,
            "next_at": self.next_at(),
        }

    def _prune(self) -> None:
        finished = sorted(
            (event for event in self._events.values() if event.status != "pending"),
            key=lambda event: event.finished_at or event.at,
        )
        overflow = len(finished) - MAX_FINISHED
        if overflow <= 0:
            return
        for event in finished[:overflow]:
            self._events.pop(event.id, None)
            self._dispatching.discard(event.id)
