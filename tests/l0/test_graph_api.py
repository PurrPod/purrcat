"""Graph 迁移规则与旧格式升级（SPEC-015）。"""

from __future__ import annotations

import json

from src.utils import graph_api


def test_upgrade_required_inputs_moves_to_global_schema():
    upgraded = graph_api.upgrade_required_inputs(
        {"required_inputs": {"topic": "主题"}, "nodes": []}
    )

    assert upgraded == {
        "global_schema": {"topic": {"required": True, "description": "主题"}},
        "nodes": [],
    }


def test_migrate_graphs_moves_file_and_keeps_backup(tmp_path):
    legacy = tmp_path / "demo.json"
    legacy.write_text(
        json.dumps({"required_inputs": {"q": "query"}, "nodes": []}),
        encoding="utf-8",
    )

    migrated = graph_api.migrate_graphs_to_folders(str(tmp_path))

    assert migrated == ["demo"]
    assert legacy.exists() is False
    assert (tmp_path / "demo.json.bak").exists()
    graph = json.loads((tmp_path / "demo" / "graph.json").read_text(encoding="utf-8"))
    assert graph["global_schema"] == {"q": {"required": True, "description": "query"}}
    assert (tmp_path / "demo" / "asset").is_dir()


def test_migrate_graphs_warns_deprecated_node_types(tmp_path):
    legacy = tmp_path / "old.json"
    legacy.write_text(
        json.dumps({"nodes": [{"type": "preview"}, {"type": "agent"}]}),
        encoding="utf-8",
    )

    graph_api.migrate_graphs_to_folders(str(tmp_path))

    note = (tmp_path / "old" / "DEPRECATED_NODES.txt").read_text(encoding="utf-8")
    assert "preview" in note
    assert "agent" not in note


def test_migrate_graphs_is_idempotent(tmp_path):
    (tmp_path / "demo").mkdir()
    (tmp_path / "demo" / "graph.json").write_text("{}", encoding="utf-8")
    legacy = tmp_path / "demo.json"
    legacy.write_text("{}", encoding="utf-8")

    assert graph_api.migrate_graphs_to_folders(str(tmp_path)) == []
    assert legacy.exists()
