"""Graph / AgentLoop 校验器的结构化结论（SPEC-013）。"""

from __future__ import annotations

from src.evolve.agentloop.validator import (
    validate_agentloop_doc,
    validate_agentloop_file,
)
from src.evolve.graph.validator import validate_graph_doc, validate_graph_folder


def _graph_doc(**overrides):
    doc = {
        "name": "demo",
        "description": "demo graph",
        "description-zh": "演示图",
        "nodes": [
            {"id": "in", "type": "task_input", "name": "输入"},
            {"id": "out", "type": "task_output", "name": "输出"},
        ],
        "edges": [{"source": "in", "target": "out"}],
    }
    doc.update(overrides)
    return doc


def test_graph_valid_doc_only_warns_on_missing_version():
    report = validate_graph_doc(_graph_doc(), expected_name="demo")
    assert report["ok"] is True
    assert report["errors"] == 0
    assert report["warnings"] == 1
    assert any(c["title"] == "声明 version" and not c["ok"] for c in report["checks"])


def test_graph_rejects_deprecated_node_type():
    doc = _graph_doc(
        nodes=[{"id": "bad", "type": "image_generator", "name": "旧节点"}],
        edges=[],
    )
    report = validate_graph_doc(doc)
    assert report["ok"] is False
    assert report["errors"] >= 1
    assert any("已废弃" in c["detail"] for c in report["checks"] if not c["ok"])


def test_graph_rejects_dangling_edge_target():
    doc = _graph_doc(edges=[{"source": "in", "target": "ghost"}])
    report = validate_graph_doc(doc)
    assert report["ok"] is False
    assert any(
        c["title"] == "所有边的 target 指向已定义节点" and not c["ok"]
        for c in report["checks"]
    )


def test_graph_non_object_doc_is_an_error():
    assert validate_graph_doc([])["errors"] == 1


def test_graph_folder_missing_file_is_an_error(tmp_path):
    report = validate_graph_folder(str(tmp_path), expected_name="demo")
    assert report["ok"] is False
    assert report["errors"] == 1


def _agentloop_doc(**overrides):
    doc = {
        "name": "demo",
        "description": "demo loop",
        "description-en": "demo loop",
        "path": "agent_vm",
        "hooks": {
            "on_build_system_prompt": [{"injection": {"content": "@RULES"}}],
        },
    }
    doc.update(overrides)
    return doc


def test_agentloop_valid_doc_is_green():
    report = validate_agentloop_doc(_agentloop_doc(), expected_name="demo")
    assert report["errors"] == 0
    assert report["warnings"] == 0
    assert report["ok"] is True
    assert any(c["title"] == "hooks 为非空映射" and c["ok"] for c in report["checks"])


def test_agentloop_unknown_stage_and_action_are_errors():
    doc = _agentloop_doc(
        hooks={
            "unknown_stage": [],
            "on_loop_start": [{"bogus": {}}],
        }
    )
    report = validate_agentloop_doc(doc)
    assert report["ok"] is False
    assert report["errors"] == 2


def test_agentloop_tool_use_check_warns_on_non_native_tool():
    doc = _agentloop_doc(
        hooks={"on_tool_calling": [{"tool_use_check": {"name": "MCP"}}]}
    )
    report = validate_agentloop_doc(doc)
    warnings = [c for c in report["checks"] if not c["ok"] and c["level"] == "warn"]
    assert any("原生工具白名单" in c["title"] for c in warnings)


def test_agentloop_missing_file_is_an_error(tmp_path):
    report = validate_agentloop_file(str(tmp_path / "missing.yaml"))
    assert report["ok"] is False
    assert report["errors"] == 1
