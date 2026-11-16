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


def _write_new_format(root, name, meta, state):
    directory = root / name
    (directory / "nodes").mkdir(parents=True)
    (directory / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False), encoding="utf-8"
    )
    (directory / "state.json").write_text(
        json.dumps(state, ensure_ascii=False), encoding="utf-8"
    )
    return directory


def test_scan_disk_tasks_reads_new_format_meta_and_state(tmp_path):
    """新格式（meta.json + state.json）也必须在任务列表里出现。"""
    _write_new_format(
        tmp_path,
        "one_t1",
        {
            "task_id": "t1",
            "name": "one",
            "graph_name": "demo",
            "create_time": "2026-02-01 10:00:00",
        },
        {"state": "completed", "total_tokens": 321},
    )

    tasks = task_store.scan_disk_tasks(str(tmp_path), log=lambda _: None)

    assert set(tasks) == {"t1"}
    assert tasks["t1"]["name"] == "one"
    assert tasks["t1"]["graph_name"] == "demo"
    assert tasks["t1"]["state"] == "completed"
    assert tasks["t1"]["token_usage"] == 321
    assert tasks["t1"]["create_time"] == "2026-02-01 10:00:00"
    assert tasks["t1"]["checkpoint_dir"] == str(tmp_path / "one_t1")


def test_load_task_checkpoint_reads_new_format(tmp_path, monkeypatch):
    """详情读取不能只认旧 checkpoint.json，新格式要能还原图谱与节点状态。"""
    monkeypatch.setattr(task_store, "DATA_DIR", str(tmp_path))
    graph = {"nodes": [{"id": "n1"}], "edges": []}
    _write_new_format(
        tmp_path / "checkpoints" / "task",
        "one_t1",
        {"task_id": "t1", "name": "one", "graph_name": "demo", "graph": graph},
        {
            "task_id": "t1",
            "state": "interrupted",
            "dag_state": {"n1": {"state": "completed"}},
            "node_state": {"n1": "completed"},
            "outputs": {"n1": {"ok": True}},
            "total_tokens": 321,
        },
    )

    data = task_store.load_task_checkpoint("t1")

    assert data["task_id"] == "t1"
    assert data["state"] == "interrupted"
    assert data["graph"] == graph
    assert data["dag_state"] == {"n1": {"state": "completed"}}
    assert data["outputs"] == {"n1": {"ok": True}}


def test_find_task_dir_prefers_exact_id_suffix(tmp_path, monkeypatch):
    """task_id 是另一个任务目录名的前缀时，不能取错目录。"""
    monkeypatch.setattr(task_store, "DATA_DIR", str(tmp_path))
    root = tmp_path / "checkpoints" / "task"
    (root / "a_t1x").mkdir(parents=True)
    (root / "z_t1").mkdir()

    assert task_store.find_task_dir("t1") == str(root / "z_t1")


def test_load_task_checkpoint_missing_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(task_store, "DATA_DIR", str(tmp_path))

    assert task_store.load_task_checkpoint("nope") is None


def test_read_log_entries_skips_invalid_lines(tmp_path):
    log_file = tmp_path / "log.jsonl"
    log_file.write_text('{"a": 1}\n\nnot-json\n{"b": 2}\n', encoding="utf-8")

    assert task_store.read_log_entries(str(log_file)) == [{"a": 1}, {"b": 2}]
    assert task_store.read_log_entries(str(tmp_path / "missing.jsonl")) == []
