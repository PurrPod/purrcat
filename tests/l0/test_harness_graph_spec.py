"""图加载、入参校验与节点实例构建（SPEC-008）。"""

from __future__ import annotations

import json

from src.harness.enums import NodeState
from src.harness.graph_spec import (
    build_node_instances,
    load_graph_file,
    validate_global_inputs,
)


def test_load_graph_file_returns_none_when_missing(tmp_path):
    assert load_graph_file(str(tmp_path), "absent") is None


def test_load_graph_file_reads_json(tmp_path):
    graph_dir = tmp_path / "demo"
    graph_dir.mkdir()
    (graph_dir / "graph.json").write_text('{"nodes": []}', encoding="utf-8")

    assert load_graph_file(str(tmp_path), "demo") == {"nodes": []}


def test_validate_global_inputs_reports_missing_and_extra():
    message = validate_global_inputs(
        {"extra": 1},
        {"topic": {"type": "string", "description": "主题", "required": True}},
    )

    assert "缺少必填参数" in message
    assert "'topic' (类型: string, 描述: 主题)" in message
    assert "传入了未知参数: 'extra'" in message
    assert "📋 有效的参数列表" in message


def test_validate_global_inputs_accepts_optional_none_and_returns_empty():
    schema = {
        "topic": {"type": "string", "required": True},
        "note": {"type": "string", "required": False},
    }

    assert validate_global_inputs({"topic": "a", "note": None}, schema) == ""


def test_build_node_instances_creates_ready_state_and_reports_unknown_type():
    nodes, types, states, err = build_node_instances(
        {"nodes": [{"id": "n1", "type": "string", "config": {"text": "hi"}}]}
    )

    assert err == ""
    assert types == {"n1": "string"}
    assert states == {"n1": NodeState.READY}
    assert "n1" in nodes

    _, _, _, err = build_node_instances(
        {"nodes": [{"id": "n2", "type": "not_a_node", "config": {}}]}
    )
    assert "节点加载失败 [not_a_node]" in err


def test_build_node_instances_explains_deprecated_type():
    _, _, _, err = build_node_instances(
        {"nodes": [{"id": "n1", "type": "preview", "config": {}}]}
    )

    assert "已在信封协议重构中移除" in err
    assert json.dumps({"ok": True})  # 保持文件内 json 引用不产生无关告警
