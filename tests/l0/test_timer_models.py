"""定时任务中心的纯逻辑（L0，SPEC-034 AC-1）。"""

from datetime import datetime

from src.timer.models import TimerEvent, next_after, resolve_catch_up


def _event(**kwargs) -> TimerEvent:
    base = {
        "id": "e1",
        "source": "test",
        "target": "main",
        "at": 1000.0,
        "effect": {"signal": "ping"},
    }
    base.update(kwargs)
    return TimerEvent(**base)


def test_interval_repeat_advances_strictly_after_now() -> None:
    """SPEC-034 AC-1：interval 按固定步长推进，结果严格晚于 now。"""
    event = _event(at=1000.0, repeat={"kind": "interval", "seconds": 60})

    assert next_after(event, 1000.0) == 1060.0
    assert next_after(event, 1001.0) == 1060.0
    assert next_after(event, 1060.0) == 1120.0
    assert next_after(event, 2100.0) == 2140.0

    future = _event(at=2000.0, repeat={"kind": "interval", "seconds": 60})
    assert next_after(future, 1500.0) == 2000.0


def test_daily_repeat_returns_next_local_occurrence() -> None:
    """SPEC-034 AC-1：daily 规则返回本地时间的下一次。"""
    anchor = datetime(2026, 1, 1, 9, 30).timestamp()
    event = _event(at=anchor, repeat={"kind": "daily", "time": "08:00"})

    nxt = next_after(event, anchor)
    assert datetime.fromtimestamp(nxt) == datetime(2026, 1, 2, 8, 0)

    before = datetime(2026, 1, 1, 7, 0).timestamp()
    assert datetime.fromtimestamp(next_after(event, before)) == datetime(
        2026, 1, 1, 8, 0
    )


def test_no_repeat_has_no_next_occurrence() -> None:
    """SPEC-034 AC-1：一次性事件不续排。"""
    assert next_after(_event(), 2000.0) is None


def test_result_round_trips_through_dict() -> None:
    """SPEC-034 AC-7：接收方回执随事件落盘，重建后仍可读取。"""
    event = _event(
        result={
            "action": "done",
            "data": {"task_id": "t1"},
            "at": 1000.0,
            "attempt": 1,
        }
    )

    restored = TimerEvent.from_dict(event.to_dict())

    assert restored.result == event.result


def test_catch_up_policy() -> None:
    """SPEC-034 AC-1：宽限内补一次，超出后顺延或过期。"""
    now = 10_000.0

    assert resolve_catch_up(_event(at=now + 10), now) == "wait"
    assert resolve_catch_up(_event(at=now - 30, catch_up="once"), now) == "fire"
    assert (
        resolve_catch_up(
            _event(
                at=now - 500,
                catch_up="once",
                repeat={"kind": "interval", "seconds": 60},
            ),
            now,
        )
        == "advance"
    )
    assert resolve_catch_up(_event(at=now - 500), now) == "expire"
    assert (
        resolve_catch_up(
            _event(at=now - 500, repeat={"kind": "interval", "seconds": 60}), now
        )
        == "advance"
    )
