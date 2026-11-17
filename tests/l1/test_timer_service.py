"""定时任务服务的集成行为（L1，SPEC-034 AC-2 ~ AC-5）。"""

import asyncio
import time

from src.timer.models import Signal, TimerEvent
from src.timer.service import TimerService
from src.timer.sinks import graph_sink
from src.timer.store import TimerStore


def _run(coro):
    return asyncio.run(coro)


def _fake_sink(calls: list, result=None):
    async def sink(event: TimerEvent) -> Signal:
        calls.append(event.id)
        if callable(result):
            return result(len(calls))
        return result or Signal("done")

    return sink


def test_due_event_fires_once(tmp_path) -> None:
    """SPEC-034 AC-2：一次性事件到点触发并完成。"""
    calls: list[str] = []

    async def scenario():
        svc = TimerService(
            store_path=str(tmp_path / "timer.json"),
            sinks={"agent": _fake_sink(calls)},
        )
        svc.add_event(
            {
                "id": "once",
                "source": "test",
                "target": "main",
                "at": time.time() + 0.05,
                "effect": {},
            }
        )
        await svc.start()
        await asyncio.sleep(0.3)
        events = svc.list_events()
        await svc.stop()
        return events

    events = _run(scenario())
    assert calls == ["once"]
    assert events[0]["status"] == "done"


def test_new_event_interrupts_idle_sleep(tmp_path) -> None:
    """SPEC-034 AC-2：新增事件立即打断等待并重新计算唤醒时刻。"""
    calls: list[str] = []

    async def scenario():
        svc = TimerService(
            store_path=str(tmp_path / "timer.json"),
            sinks={"agent": _fake_sink(calls)},
        )
        svc.add_event(
            {
                "id": "late",
                "source": "test",
                "target": "main",
                "at": time.time() + 10,
                "effect": {},
            }
        )
        await svc.start()
        await asyncio.sleep(0.05)
        svc.add_event(
            {
                "id": "early",
                "source": "test",
                "target": "main",
                "at": time.time() + 0.05,
                "effect": {},
            }
        )
        await asyncio.sleep(0.3)
        await svc.stop()

    _run(scenario())
    assert calls == ["early"]


def test_defer_reschedules_and_repeat_advances(tmp_path) -> None:
    """SPEC-034 AC-3：defer 重排，重复事件按规则续排。"""
    deferred_calls: list[str] = []

    def defer_once(count: int) -> Signal:
        return Signal("defer", defer=0.05) if count == 1 else Signal("done")

    async def scenario():
        svc = TimerService(
            store_path=str(tmp_path / "timer.json"),
            sinks={"agent": _fake_sink(deferred_calls, defer_once)},
        )
        svc.add_event(
            {
                "id": "defer",
                "source": "test",
                "target": "main",
                "at": time.time() + 0.02,
                "effect": {},
            }
        )
        await svc.start()
        await asyncio.sleep(0.3)
        status = svc.list_events()[0]["status"]
        await svc.stop()
        return status

    assert _run(scenario()) == "done"
    assert len(deferred_calls) == 2

    repeat_calls: list[str] = []

    async def repeat_scenario():
        svc = TimerService(
            store_path=str(tmp_path / "repeat.json"),
            sinks={"agent": _fake_sink(repeat_calls)},
        )
        svc.add_event(
            {
                "id": "repeat",
                "source": "test",
                "target": "main",
                "at": time.time() + 0.02,
                "repeat": {"kind": "interval", "seconds": 0.05},
                "effect": {},
            }
        )
        await svc.start()
        await asyncio.sleep(0.25)
        svc.cancel("repeat")
        await svc.stop()

    _run(repeat_scenario())
    assert len(repeat_calls) >= 2


def test_dedupe_and_source_reconcile(tmp_path) -> None:
    """SPEC-034 AC-4：dedupe_key 覆盖旧事件，来源可声明式替换。"""
    svc = TimerService(store_path=str(tmp_path / "timer.json"), sinks={})
    base = {"source": "note:2026-01-01", "target": "main", "effect": {}}

    svc.add_event({**base, "id": "a", "at": 100.0, "dedupe_key": "same"})
    svc.add_event({**base, "id": "b", "at": 200.0, "dedupe_key": "same"})
    assert [
        event["id"] for event in svc.list_events() if event["status"] == "pending"
    ] == ["b"]

    svc.replace_source(
        "note:2026-01-01",
        [
            {**base, "id": "b", "at": 300.0},
            {**base, "id": "c", "at": 400.0},
        ],
    )
    events = [
        event
        for event in svc.list_events(source="note:2026-01-01")
        if event["status"] == "pending"
    ]
    assert sorted(e["id"] for e in events) == ["b", "c"]
    assert next(e for e in events if e["id"] == "b")["at"] == 300.0

    svc.replace_source("note:2026-01-01", [{**base, "id": "c", "at": 400.0}])
    events = svc.list_events(source="note:2026-01-01")
    assert [e["id"] for e in events if e["status"] == "pending"] == ["c"]


def test_restart_catch_up_policy(tmp_path) -> None:
    """SPEC-034 AC-5：宽限内补一次，超出后顺延或过期。"""
    path = str(tmp_path / "timer.json")
    now = time.time()
    store = TimerStore(path)
    store.upsert(
        TimerEvent(
            id="grace",
            source="test",
            target="main",
            at=now - 10,
            catch_up="once",
        )
    )
    store.upsert(
        TimerEvent(
            id="stale-once",
            source="test",
            target="main",
            at=now - 500,
            catch_up="once",
        )
    )
    store.upsert(
        TimerEvent(
            id="repeat",
            source="test",
            target="main",
            at=now - 500,
            repeat={"kind": "interval", "seconds": 3600},
        )
    )
    store.save()

    async def scenario():
        calls: list[str] = []
        svc = TimerService(store_path=path, sinks={"agent": _fake_sink(calls)})
        await svc.start()
        await asyncio.sleep(0.15)
        events = {e["id"]: e for e in svc.list_events()}
        await svc.stop()
        return calls, events

    calls, events = _run(scenario())
    assert calls == ["grace"]
    assert events["grace"]["status"] == "done"
    assert events["stale-once"]["status"] == "done"
    assert events["repeat"]["status"] == "pending"
    assert events["repeat"]["at"] > time.time()


def test_target_result_is_persisted_and_published(tmp_path) -> None:
    """SPEC-034 AC-7：target 回执写入事件并随 SSE 广播回传给 source。"""
    published: list[dict] = []

    async def sink(event: TimerEvent) -> Signal:
        return Signal("done", data={"task_id": "task-1"})

    async def scenario():
        svc = TimerService(
            store_path=str(tmp_path / "timer.json"),
            sinks={"agent": sink},
        )
        unsubscribe = svc.subscribe(published.append)
        svc.add_event(
            {
                "id": "ack",
                "source": "plugin:demo",
                "target": "main",
                "at": time.time() + 0.02,
                "effect": {},
            }
        )
        await svc.start()
        await asyncio.sleep(0.2)
        event = svc.list_events()[0]
        await svc.stop()
        unsubscribe()
        return event

    event = _run(scenario())
    assert event["status"] == "done"
    assert event["result"]["action"] == "done"
    assert event["result"]["data"] == {"task_id": "task-1"}
    assert event["result"]["attempt"] == 1
    assert published[-1]["result"]["data"] == {"task_id": "task-1"}


def test_graph_sink_ack_contains_task_id(monkeypatch) -> None:
    """SPEC-034 AC-7：graph sink 立即回执 task_id，source 可据此跟踪任务。"""
    import src.harness.process as process

    class FakeTask:
        def __init__(self, task_name, graph_name, inputs):
            self.task_id = "task-42"
            self.task_name = task_name

        async def run(self):
            return None

    monkeypatch.setattr(process, "Task", FakeTask)

    async def scenario():
        return await graph_sink(
            TimerEvent(
                id="t1",
                source="plugin:demo",
                target="graph:daily",
                at=time.time(),
                effect={"payload": {"task_name": "daily-run"}},
            )
        )

    signal = _run(scenario())
    assert signal.action == "done"
    assert signal.data["task_id"] == "task-42"
    assert signal.data["graph"] == "daily"
