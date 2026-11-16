"""任务列表：磁盘摘要按目录结构缓存，避免轮询时反复解析 meta/state.json。"""

from __future__ import annotations

import json

from src.utils import task_api, task_store


def _write_task(root, task_id: str, name: str, state: str):
    directory = root / f"{name}_{task_id}"
    directory.mkdir(parents=True)
    (directory / "meta.json").write_text(
        json.dumps(
            {
                "task_id": task_id,
                "name": name,
                "graph_name": "demo",
                "create_time": "2026-02-01 10:00:00",
            }
        ),
        encoding="utf-8",
    )
    (directory / "state.json").write_text(
        json.dumps({"state": state}), encoding="utf-8"
    )


def test_get_task_list_reuses_disk_scan_until_dir_set_changes(tmp_path, monkeypatch):
    monkeypatch.setattr(task_store, "checkpoints_root", lambda: str(tmp_path))
    monkeypatch.setattr(
        task_api, "_disk_summary_cache", {"signature": None, "tasks": {}}
    )
    monkeypatch.setattr(task_api, "TASK_INSTANCES", {})
    real_scan = task_store.scan_disk_tasks
    calls: list = []
    monkeypatch.setattr(
        task_store,
        "scan_disk_tasks",
        lambda base: (calls.append(base), real_scan(base))[1],
    )
    _write_task(tmp_path, "t1", "one", "completed")

    task_api.get_task_list()
    second = task_api.get_task_list()

    assert len(calls) == 1
    assert [t["id"] for t in second] == ["t1"]

    _write_task(tmp_path, "t2", "two", "idle")
    third = task_api.get_task_list()

    assert len(calls) == 2
    assert {t["id"] for t in third} == {"t1", "t2"}
