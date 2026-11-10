"""任务状态视图组装的 L0 用例（SPEC-021）。"""

from __future__ import annotations

from src.server.api import task_views


class _Task:
    def __init__(self, node_memory):
        self.node_memory = node_memory


def test_collect_frontend_memory_merges_memory_and_disk(tmp_path):
    """SPEC-021：内存强制指令与节点落盘消息按 node_id 合并。"""
    checkpoint = tmp_path / "checkpoint"
    nodes = checkpoint / "nodes"
    (nodes / "n1").mkdir(parents=True)
    (nodes / "n1" / "memory.jsonl").write_text(
        '{"role": "user"}\n{"role": "assistant"}\n', encoding="utf-8"
    )
    (nodes / "n2").mkdir()
    (nodes / "n2" / "live_memory.json").write_text(
        '[{"role": "user"}]', encoding="utf-8"
    )
    (nodes / "n3").mkdir()
    (nodes / "n3" / "outputs.json").write_text(
        '{"messages": [{"role": "assistant"}]}', encoding="utf-8"
    )

    out = task_views.collect_frontend_memory(
        "t1", {"t1": _Task({"n1": {"instructions": ["do it"]}})}, str(checkpoint)
    )

    assert out["n1"]["instructions"] == ["do it"]
    assert out["n1"]["messages"] == [{"role": "user"}, {"role": "assistant"}]
    assert out["n2"]["messages"] == [{"role": "user"}]
    assert out["n3"]["messages"] == [{"role": "assistant"}]


def test_collect_frontend_memory_without_checkpoint_keeps_memory_only():
    """SPEC-021：缺少 checkpoint 时只回传内存中的 node_memory 深拷贝。"""
    out = task_views.collect_frontend_memory(
        "t1", {"t1": _Task({"n1": {"instructions": ["x"]}})}, None
    )

    assert out == {"n1": {"instructions": ["x"]}}
    assert out is not None


def test_locate_checkpoint_dir_prefers_instance_then_suffix_match(tmp_path):
    """SPEC-021：checkpoint 定位内存优先，磁盘按任务 id 后缀兜底。"""

    class _WithDir:
        checkpoint_dir = "/memory/cp"

    assert (
        task_views.locate_checkpoint_dir("t1", {"t1": _WithDir()}, str(tmp_path))
        == "/memory/cp"
    )

    (tmp_path / "20260101_t1").mkdir()
    assert task_views.locate_checkpoint_dir("t1", {}, str(tmp_path)) == str(
        tmp_path / "20260101_t1"
    )
    assert task_views.locate_checkpoint_dir("missing", {}, str(tmp_path)) is None


def test_group_logs_by_node_defaults_to_system():
    """SPEC-021：日志按 node_id 分组，缺省归入 system 且保持原顺序。"""
    logs = [{"node_id": "a", "msg": 1}, {"msg": 2}, {"node_id": "a", "msg": 3}]

    assert task_views.group_logs_by_node(logs) == {
        "a": [{"node_id": "a", "msg": 1}, {"node_id": "a", "msg": 3}],
        "system": [{"msg": 2}],
    }
