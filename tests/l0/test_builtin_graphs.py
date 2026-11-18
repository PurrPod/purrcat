"""内置图集合（default / skill_eval）的播种、修复与模板契约（SPEC-040）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.evolve.graph.validator import validate_graph_folder
from src.harness.graph_init import (
    BUILTIN_GRAPH_NAMES,
    DEFAULT_GRAPH_NAME,
    SKILL_EVAL_GRAPH_NAME,
    TEMPLATES_DIR,
    ensure_builtin_graphs,
)
from src.harness.graph_spec import build_node_instances


def _load_template(name: str) -> dict:
    path = Path(TEMPLATES_DIR) / name / "graph.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", BUILTIN_GRAPH_NAMES)
def test_template_exists_and_name_matches_folder(name: str):
    assert _load_template(name)["name"] == name


def test_ensure_seeds_every_builtin_graph(tmp_path):
    assert sorted(ensure_builtin_graphs(str(tmp_path))) == sorted(BUILTIN_GRAPH_NAMES)
    for name in BUILTIN_GRAPH_NAMES:
        assert (tmp_path / name / "graph.json").is_file()


def test_ensure_skips_when_all_builtin_graphs_match(tmp_path):
    ensure_builtin_graphs(str(tmp_path))

    assert ensure_builtin_graphs(str(tmp_path)) == []


@pytest.mark.parametrize("name", BUILTIN_GRAPH_NAMES)
def test_ensure_restores_modified_builtin_graph(tmp_path, name: str):
    ensure_builtin_graphs(str(tmp_path))
    target = tmp_path / name / "graph.json"
    target.write_text('{"name": "tampered"}', encoding="utf-8")

    assert ensure_builtin_graphs(str(tmp_path)) == [name]
    assert target.read_text(encoding="utf-8") == (
        Path(TEMPLATES_DIR) / name / "graph.json"
    ).read_text(encoding="utf-8")


def test_skill_eval_template_passes_graph_validation():
    report = validate_graph_folder(
        str(Path(TEMPLATES_DIR) / SKILL_EVAL_GRAPH_NAME),
        expected_name=SKILL_EVAL_GRAPH_NAME,
    )

    assert report["errors"] == 0
    assert report["warnings"] == 0


def test_skill_eval_template_instantiates_all_nodes():
    _, _, _, err = build_node_instances(_load_template(SKILL_EVAL_GRAPH_NAME))

    assert err == ""


def test_skill_eval_keeps_runner_contract():
    """盲测运行器依赖这些入参、节点 id 与输出键，改名会静默判负。"""
    doc = _load_template(SKILL_EVAL_GRAPH_NAME)

    assert set(doc["global_schema"]) == {
        "host_skill_md_path",
        "workplace_dir",
        "prompt",
        "expected_output",
    }
    assert any(
        node["id"] == "nd_agent_exec" and node["type"] == "agent_loop"
        for node in doc["nodes"]
    )
    outputs = {
        var["name"]
        for node in doc["nodes"]
        if node["type"] == "task_output"
        for var in node["config"]["target_vars"]
    }
    assert outputs == {"exec_summary", "eval_result"}


def test_skill_eval_does_not_wire_the_removed_card_role_port():
    """message_card_builder 只输出 role=user，旧的 role 连线已失效。"""
    doc = _load_template(SKILL_EVAL_GRAPH_NAME)

    assert all(edge.get("targetHandle") != "role" for edge in doc["edges"])
    assert all(node["id"] != "string_system_role" for node in doc["nodes"])


def test_skill_eval_injects_worker_and_judge_personas():
    """人设走 agent_loop 的 on_build_system_prompt，而非已移除的卡片 role。"""
    doc = _load_template(SKILL_EVAL_GRAPH_NAME)
    loops = {
        node["id"]: node["config"]["value"]
        for node in doc["nodes"]
        if node["id"] in ("string_agentloop_exec", "string_agentloop_eval")
    }

    assert set(loops) == {"string_agentloop_exec", "string_agentloop_eval"}
    assert all("on_build_system_prompt" in value for value in loops.values())


def test_default_is_still_part_of_the_builtin_bundle():
    assert DEFAULT_GRAPH_NAME in BUILTIN_GRAPH_NAMES
