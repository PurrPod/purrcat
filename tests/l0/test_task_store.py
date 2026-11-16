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


def test_scan_disk_tasks_demotes_stale_running_state(tmp_path):
    """重启后扫盘不可能还有 running，列表必须展示为 interrupted。"""
    _write_new_format(
        tmp_path,
        "one_t1",
        {"task_id": "t1", "name": "one"},
        {"state": "running"},
    )

    tasks = task_store.scan_disk_tasks(str(tmp_path), log=lambda _: None)

    assert tasks["t1"]["state"] == "interrupted"


def test_build_disk_task_demotes_stale_running_state():
    summary = task_store.build_disk_task(
        {"task_id": "t1", "name": "legacy", "state": "running"}, "x"
    )

    assert summary["state"] == "interrupted"


def test_load_task_checkpoint_demotes_stale_running_nodes(tmp_path, monkeypatch):
    """详情里的任务与节点同样不能残留 running，节点回落到 ready。"""
    monkeypatch.setattr(task_store, "DATA_DIR", str(tmp_path))
    _write_new_format(
        tmp_path / "checkpoints" / "task",
        "one_t1",
        {"task_id": "t1", "name": "one"},
        {
            "state": "running",
            "dag_state": {"n1": {"state": "running"}, "n2": {"state": "completed"}},
            "node_state": {"n1": "running", "n2": "completed"},
        },
    )

    data = task_store.load_task_checkpoint("t1")

    assert data["state"] == "interrupted"
    assert data["dag_state"] == {"n1": {"state": "ready"}, "n2": {"state": "completed"}}
    assert data["node_state"] == {"n1": "ready", "n2": "completed"}


def test_load_task_checkpoint_normalizes_legacy_running(tmp_path, monkeypatch):
    """旧格式详情也不能把残留 running 透给前端。"""
    monkeypatch.setattr(task_store, "DATA_DIR", str(tmp_path))
    _write_checkpoint(
        tmp_path / "checkpoints" / "task",
        "old_t9",
        {
            "task_id": "t9",
            "name": "old",
            "state": "running",
            "dag_state": {"n1": {"state": "running"}},
        },
    )

    data = task_store.load_task_checkpoint("t9")

    assert data["state"] == "interrupted"
    assert data["dag_state"] == {"n1": {"state": "ready"}}


def test_reconcile_disk_task_states_rewrites_stale_running(tmp_path):
    """对账要把磁盘上的残留运行态修好，且不动已结束任务。"""
    running_dir = _write_new_format(
        tmp_path,
        "one_t1",
        {"task_id": "t1", "name": "one"},
        {
            "state": "running",
            "dag_state": {"n1": {"state": "running"}},
            "node_state": {"n1": "running"},
        },
    )
    done_dir = _write_new_format(
        tmp_path,
        "two_t2",
        {"task_id": "t2", "name": "two"},
        {"state": "completed", "node_state": {"n1": "completed"}},
    )
    done_before = (done_dir / "state.json").read_text(encoding="utf-8")

    fixed = task_store.reconcile_disk_task_states(str(tmp_path), log=lambda _: None)

    assert fixed == ["t1"]
    saved = json.loads((running_dir / "state.json").read_text(encoding="utf-8"))
    assert saved["state"] == "interrupted"
    assert saved["dag_state"] == {"n1": {"state": "ready"}}
    assert saved["node_state"] == {"n1": "ready"}
    assert (done_dir / "state.json").read_text(encoding="utf-8") == done_before


def test_reconcile_disk_task_states_skips_active_tasks(tmp_path):
    _write_new_format(tmp_path, "one_t1", {"task_id": "t1"}, {"state": "running"})

    fixed = task_store.reconcile_disk_task_states(
        str(tmp_path), skip_ids={"t1"}, log=lambda _: None
    )

    assert fixed == []


def test_reconcile_disk_task_states_leaves_legacy_checkpoint(tmp_path):
    """旧格式 checkpoint.json 可能很大，启动对账不读不写，由展示层归一化。"""
    directory = _write_checkpoint(
        tmp_path, "old_t9", {"task_id": "t9", "state": "running"}
    )

    fixed = task_store.reconcile_disk_task_states(str(tmp_path), log=lambda _: None)

    assert fixed == []
    saved = json.loads((directory / "checkpoint.json").read_text(encoding="utf-8"))
    assert saved["state"] == "running"


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
