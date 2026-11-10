"""任务 checkpoint 的磁盘扫描、合并与排序（SPEC-015）。"""

from __future__ import annotations

import json

from src.utils import task_store


def _write_checkpoint(root, name, data):
    directory = root / name
    directory.mkdir(parents=True)
    (directory / "checkpoint.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )
    return directory


def test_build_disk_task_falls_back_to_file_time():
    summary = task_store.build_disk_task(
        {"task_id": "t1", "name": "demo"}, "2026-01-01 00:00:00"
    )

    assert summary == {
        "id": "t1",
        "name": "demo",
        "graph_name": "default",
        "state": "idle",
        "step": 0,
        "expert_type": "Task",
        "create_time": "2026-01-01 00:00:00",
        "token_usage": 0,
        "checkpoint_dir": "",
    }
    assert task_store.build_disk_task({"name": "no-id"}, "x") is None


def test_sort_task_summaries_is_newest_first():
    items = [{"id": "a", "create_time": "2026-01-01"}, {"id": "b", "create_time": ""}]

    assert [item["id"] for item in task_store.sort_task_summaries(items)] == ["a", "b"]


def test_scan_disk_tasks_reads_checkpoints_and_skips_broken(tmp_path):
    _write_checkpoint(
        tmp_path,
        "t1",
        {"task_id": "t1", "name": "one", "create_time": "2026-01-02 00:00:00"},
    )
    broken = tmp_path / "t2"
    broken.mkdir()
    (broken / "checkpoint.json").write_text("{broken", encoding="utf-8")
    logs = []

    tasks = task_store.scan_disk_tasks(str(tmp_path), log=logs.append)

    assert set(tasks) == {"t1"}
    assert tasks["t1"]["create_time"] == "2026-01-02 00:00:00"
    assert any("读取历史任务 t2 失败" in line for line in logs)


def test_read_log_entries_skips_invalid_lines(tmp_path):
    log_file = tmp_path / "log.jsonl"
    log_file.write_text('{"a": 1}\n\nnot-json\n{"b": 2}\n', encoding="utf-8")

    assert task_store.read_log_entries(str(log_file)) == [{"a": 1}, {"b": 2}]
    assert task_store.read_log_entries(str(tmp_path / "missing.jsonl")) == []
