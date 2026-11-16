"""默认图初始化与缺省派发（SPEC-027）。"""

from __future__ import annotations

import json
from pathlib import Path

from src.harness.graph_init import (
    DEFAULT_GRAPH_NAME,
    TEMPLATES_DIR,
    ensure_default_graph,
)
from src.harness.graph_spec import build_node_instances, load_graph_file


def _seed_and_load(tmp_path) -> dict:
    assert ensure_default_graph(str(tmp_path)) is True
    graph = load_graph_file(str(tmp_path), DEFAULT_GRAPH_NAME)
    assert graph is not None
    return graph


def test_seeds_a_real_graph_json_into_user_graph_dir(tmp_path):
    graph = _seed_and_load(tmp_path)
    graph_file = tmp_path / DEFAULT_GRAPH_NAME / "graph.json"

    assert graph_file.is_file()
    assert json.loads(graph_file.read_text(encoding="utf-8")) == graph
    assert graph["name"] == DEFAULT_GRAPH_NAME


def test_seed_never_overwrites_existing_graph(tmp_path):
    _seed_and_load(tmp_path)
    graph_file = tmp_path / DEFAULT_GRAPH_NAME / "graph.json"
    graph_file.write_text('{"name": "default", "user": true}', encoding="utf-8")

    assert ensure_default_graph(str(tmp_path)) is False
    assert json.loads(graph_file.read_text(encoding="utf-8"))["user"] is True


def test_seed_skips_gracefully_when_template_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "src.harness.graph_init.TEMPLATES_DIR", str(tmp_path / "missing")
    )

    assert ensure_default_graph(str(tmp_path / "graphs")) is False


def test_default_graph_schema_has_only_prompt(tmp_path):
    graph = _seed_and_load(tmp_path)

    assert list(graph["global_schema"]) == ["prompt"]
    assert graph["global_schema"]["prompt"]["required"] is True
    assert graph["global_schema"]["prompt"]["type"] == "string"
    assert "可选" in graph["global_schema"]["prompt"]["description"]


def test_default_graph_instantiates_all_nodes_and_edges(tmp_path):
    graph = _seed_and_load(tmp_path)

    _, _, _, err = build_node_instances(graph)
    assert err == ""

    node_ids = {node["id"] for node in graph["nodes"]}
    assert graph["nodes"]
    assert graph["edges"]
    for edge in graph["edges"]:
        assert edge["source"] in node_ids
        assert edge["target"] in node_ids


def test_default_graph_system_prompt_enforces_spec_workflow(tmp_path):
    text = "\n".join(
        node.get("config", {}).get("value", "")
        for node in _seed_and_load(tmp_path)["nodes"]
        if node["type"] == "string"
    )

    assert "Spec" in text
    assert "执行计划" in text
    assert "执行进度" in text
    assert "自动通知" in text
    assert "没有 Spec" in text
    assert "直接按 prompt 执行" in text
    assert "不要编造或新建 Spec 文件" in text
    # 系统提示词由 agent_loop 的 on_build_system_prompt 注入为 system_input 卡片
    assert "on_build_system_prompt" in text


def test_default_graph_description_keeps_spec_optional(tmp_path):
    description = _seed_and_load(tmp_path)["description"]

    assert "default" in description.lower()
    assert "spec" in description.lower()
    assert "optional" in description.lower()
    assert "no spec" in description.lower()


def test_template_is_the_checked_in_graph_json():
    template = Path(TEMPLATES_DIR) / DEFAULT_GRAPH_NAME / "graph.json"

    assert template.is_file()
    assert (
        json.loads(template.read_text(encoding="utf-8"))["name"] == DEFAULT_GRAPH_NAME
    )


def test_load_graph_file_returns_none_before_seed(tmp_path):
    assert load_graph_file(str(tmp_path), DEFAULT_GRAPH_NAME) is None


def test_list_graphs_includes_default_after_seed(monkeypatch, tmp_path):
    from src.tool.task import task as task_module

    ensure_default_graph(str(tmp_path))
    monkeypatch.setattr("src.utils.config.GRAPHS_DIR", str(tmp_path))

    assert DEFAULT_GRAPH_NAME in task_module._get_all_graphs_info()


def test_add_without_graph_name_uses_default(monkeypatch):
    from src.tool.task import task as task_module

    captured = {}

    monkeypatch.setattr(
        task_module,
        "_get_all_graphs_info",
        lambda: {
            DEFAULT_GRAPH_NAME: {
                "description": "default worker",
                "core": "openai:deepseek-v4-flash",
                "param_schema": {"prompt": {"type": "string", "required": True}},
            }
        },
    )

    def fake_add(name, inputs, graph_name):
        captured.update(name=name, inputs=inputs, graph_name=graph_name)
        return {"task_id": "t1", "message": "ok"}, None

    monkeypatch.setattr(task_module, "add_task_operation", fake_add)

    task_module._handle_add(name="demo", inputs={"prompt": "do it"})

    assert captured["graph_name"] == DEFAULT_GRAPH_NAME
    assert captured["inputs"] == {"prompt": "do it"}


def test_add_with_explicit_default_graph_name(monkeypatch):
    from src.tool.task import task as task_module

    captured = {}

    monkeypatch.setattr(
        task_module,
        "_get_all_graphs_info",
        lambda: {
            DEFAULT_GRAPH_NAME: {
                "description": "default worker",
                "core": "openai:deepseek-v4-flash",
                "param_schema": {"prompt": {"type": "string", "required": True}},
            }
        },
    )

    def fake_add(name, inputs, graph_name):
        captured.update(name=name, graph_name=graph_name)
        return {"task_id": "t2", "message": "ok"}, None

    monkeypatch.setattr(task_module, "add_task_operation", fake_add)

    task_module._handle_add(
        name="demo", graph_name="default", inputs={"prompt": "do it"}
    )

    assert captured["graph_name"] == "default"
