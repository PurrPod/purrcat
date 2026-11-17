"""任务耗时查询与任务目录名清洗（SPEC-035）。"""

from __future__ import annotations

import threading
import time

from src.harness.process import safe_task_dir_name
from src.utils import task_api, task_store


class _FakeTask:
    def __init__(self, state: str, execution_time: float, started_at=None, finished_at=None):
        self.task_id = "t1"
        self.state = type("S", (), {"value": state})()
        self.execution_time = execution_time
        self.started_at = started_at
        self.finished_at = finished_at
        self._lock = threading.Lock()


def test_running_task_adds_current_session(monkeypatch):
    """SPEC-035 AC-1：运行中返回累计耗时 + 本次运行至今。"""
    task = _FakeTask("running", 10.0, started_at=time.time() - 5)
    monkeypatch.setattr(task_api, "TASK_INSTANCES", {"t1": task})
    monkeypatch.setattr(task_store, "load_task_checkpoint", lambda _tid: None)

    data = task_api.get_task_elapsed("t1")
    assert data["task_id"] == "t1"
    assert data["state"] == "running"
    assert 14.0 <= data["elapsed"] <= 17.0


def test_completed_task_returns_accumulated_time(monkeypatch):
    """SPEC-035 AC-1：终态不再叠加当前时刻。"""
    task = _FakeTask("completed", 42.5, started_at=time.time() - 100, finished_at=time.time())
    monkeypatch.setattr(task_api, "TASK_INSTANCES", {"t1": task})
    monkeypatch.setattr(task_store, "load_task_checkpoint", lambda _tid: None)

    data = task_api.get_task_elapsed("t1")
    assert data["elapsed"] == 42.5
    assert data["elapsed_ms"] == 42500


def test_dormant_task_reads_checkpoint_snapshot(monkeypatch):
    """SPEC-035 AC-2：休眠任务读 state.json。"""
    monkeypatch.setattr(task_api, "TASK_INSTANCES", {})
    monkeypatch.setattr(
        task_store,
        "load_task_checkpoint",
        lambda _tid: {"state": "completed", "execution_time": 7.25, "started_at": 1.0},
    )

    data = task_api.get_task_elapsed("t2")
    assert data["elapsed"] == 7.25
    assert data["started_at"] == 1.0


def test_missing_task_returns_none(monkeypatch):
    """SPEC-035 AC-2：任务不存在返回 None，接口层转 404。"""
    monkeypatch.setattr(task_api, "TASK_INSTANCES", {})
    monkeypatch.setattr(task_store, "load_task_checkpoint", lambda _tid: None)

    assert task_api.get_task_elapsed("missing") is None


def test_safe_task_dir_name_strips_windows_reserved_chars():
    """SPEC-035 AC-3：任务名里的冒号等不能进入目录名。"""
    assert safe_task_dir_name("note:2026-11-17:写周报") == "note_2026-11-17_写周报"
    assert "/" not in safe_task_dir_name("a/b\\c")
    assert safe_task_dir_name("") == "task"
    assert safe_task_dir_name("...") == "task"
