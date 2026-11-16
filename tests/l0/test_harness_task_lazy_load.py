"""任务实例按需加载：启动时不再全量扫盘载入内存。"""

from __future__ import annotations

from src.harness import process


def _bare_task(task_id: str):
    task = object.__new__(process.Task)
    task.task_id = task_id
    return task


def test_startup_no_longer_bulk_loads_tasks():
    assert not hasattr(process, "auto_load_all_tasks")


def test_load_task_instance_returns_cached_instance():
    task = _bare_task("cached-1")
    process.TASK_INSTANCES["cached-1"] = task
    try:
        assert process.load_task_instance("cached-1") is task
    finally:
        process.TASK_INSTANCES.pop("cached-1", None)


def test_load_task_instance_reads_checkpoint_on_demand(tmp_path, monkeypatch):
    task_dir = tmp_path / "demo_abc"
    task_dir.mkdir()
    loaded = _bare_task("abc")
    calls: list = []
    monkeypatch.setattr(
        "src.utils.task_store.find_task_dir", lambda _tid: str(task_dir)
    )
    monkeypatch.setattr(
        process.Task,
        "load_checkpoint",
        staticmethod(lambda path: calls.append(path) or loaded),
    )

    assert process.load_task_instance("abc") is loaded
    assert calls == [str(task_dir)]


def test_load_task_instance_returns_none_when_checkpoint_missing(monkeypatch):
    monkeypatch.setattr("src.utils.task_store.find_task_dir", lambda _tid: None)

    assert process.load_task_instance("missing") is None
