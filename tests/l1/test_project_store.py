"""项目存储：索引读写、记忆文件创建、旧文件迁移与非法 ID 防护。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agent import project_store


@pytest.fixture
def store(tmp_path, monkeypatch):
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    monkeypatch.setattr(project_store, "PROJECTS_DIR", str(projects_dir))
    monkeypatch.setattr(
        project_store, "PROJECT_INDEX_PATH", str(projects_dir / "index.json")
    )
    return project_store.ProjectStore


def test_create_list_get_and_delete_roundtrip(store):
    created = store.create_project("  测试项目  ")

    assert created["name"] == "测试项目"
    assert created["id"].startswith("project_")
    assert [item["id"] for item in store.list_projects()] == [created["id"]]
    assert store.get_project(created["id"])["name"] == "测试项目"

    memory = Path(store.memory_path(created["id"]))
    assert memory.is_file()
    assert "测试项目" in memory.read_text(encoding="utf-8")

    assert store.delete_project(created["id"]) is True
    assert store.list_projects() == []
    assert not Path(store._project_dir(created["id"])).exists()
    assert store.delete_project(created["id"]) is False


def test_update_project_name_and_timestamp(store):
    created = store.create_project("旧名字")

    updated = store.update_project(created["id"], name="新名字")

    assert updated["name"] == "新名字"
    assert updated["id"] == created["id"]
    assert store.update_project("project_missing", name="x") is None


def test_blank_names_are_rejected(store):
    with pytest.raises(ValueError):
        store.create_project("   ")
    created = store.create_project("有效")
    with pytest.raises(ValueError):
        store.update_project(created["id"], name="  ")


@pytest.mark.parametrize(
    "bad_id",
    ["", None, "project_", "../../etc", "project_../../x", "other_123"],
)
def test_invalid_ids_are_rejected_without_touching_disk(store, bad_id):
    assert store.get_project(bad_id) is None


def test_prompt_block_mentions_memory_path(store):
    created = store.create_project("项目A")

    block = store.prompt_block(created["id"])

    assert "项目A" in block
    assert store.memory_path(created["id"]) in block
    assert "MEMORY.md" in block


def test_legacy_project_file_is_migrated(store):
    created = store.create_project("旧格式")
    memory = Path(store.memory_path(created["id"]))
    legacy = memory.with_name(store.LEGACY_FILENAME)
    memory.rename(legacy)
    assert legacy.exists()

    projects = store.list_projects()

    assert projects[0]["id"] == created["id"]
    assert memory.exists()
    assert not legacy.exists()


def test_corrupt_index_is_tolerated(store):
    index = Path(project_store.PROJECT_INDEX_PATH)
    index.write_text("{ not json", encoding="utf-8")

    assert store.list_projects() == []
    assert store.get_project("project_abc") is None


def test_non_dict_index_entries_are_ignored(store):
    index = Path(project_store.PROJECT_INDEX_PATH)
    index.write_text(json.dumps({"projects": ["x", 1, None]}), encoding="utf-8")

    assert store.list_projects() == []
