"""沙盒挂载配置、别名与 /mount 路径映射（SPEC-045）。"""

from __future__ import annotations

import json
import os

import pytest

from src.utils import sandbox_mounts as sm


@pytest.fixture
def mount_cfg(tmp_path, monkeypatch):
    path = tmp_path / "mounts.json"
    monkeypatch.setattr(sm, "MOUNTS_CONFIG_PATH", str(path))
    return path


def test_suggest_name_appends_case_insensitive_suffix():
    base = os.path.join("work", "src")

    assert sm.suggest_name(base, []) == "src"
    assert sm.suggest_name(base, ["src"]) == "src-2"
    assert sm.suggest_name(base, ["src", "SRC-2"]) == "src-3"


def test_sanitize_name_replaces_invalid_characters():
    assert sm.sanitize_name("my folder!") == "my-folder"
    assert sm.sanitize_name("中文") == "mount"


def test_validate_rejects_duplicate_missing_and_nested_directories(tmp_path):
    root = tmp_path / "work"
    (root / "sub").mkdir(parents=True)
    mounts = [{"name": "work", "source": str(root)}]

    with pytest.raises(sm.MountError):
        sm.validate_new_mount(str(root), mounts=mounts)
    with pytest.raises(sm.MountError):
        sm.validate_new_mount(str(root / "sub"), mounts=mounts)
    with pytest.raises(sm.MountError):
        sm.validate_new_mount(str(tmp_path / "missing"), mounts=[])


def test_validate_rejects_source_overlapping_agent_vm(tmp_path, monkeypatch):
    agent_vm = tmp_path / "data" / "agent_vm"
    (agent_vm / "notes").mkdir(parents=True)
    monkeypatch.setattr(sm, "AGENT_VM_DIR", str(agent_vm))

    with pytest.raises(sm.MountError):
        sm.validate_new_mount(str(tmp_path / "data"), mounts=[])
    with pytest.raises(sm.MountError):
        sm.validate_new_mount(str(agent_vm / "notes"), mounts=[])


def test_validate_rejects_invalid_custom_name(tmp_path):
    source = tmp_path / "proj"
    source.mkdir()

    with pytest.raises(sm.MountError):
        sm.validate_new_mount(str(source), name="bad/name", mounts=[])


def test_resolve_mount_path_maps_alias_and_blocks_traversal(tmp_path):
    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    mounts = [{"name": "proj", "source": str(root)}]

    mapped = sm.resolve_mount_path("/mount/proj/src/a.txt", mounts)
    assert mapped == os.path.abspath(os.path.join(str(root), "src", "a.txt"))
    assert sm.resolve_mount_path(r"/mount\proj\a.txt", mounts) == os.path.abspath(
        os.path.join(str(root), "a.txt")
    )
    assert sm.resolve_mount_path("/mount/PROJ/a.txt", mounts) == os.path.abspath(
        os.path.join(str(root), "a.txt")
    )
    assert sm.resolve_mount_path("/mount/proj/../secret", mounts) is None
    assert sm.resolve_mount_path("/mount/other/a.txt", mounts) is None
    assert sm.resolve_mount_path("/mount", mounts) is None


def test_is_in_mount_source_distinguishes_siblings(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    mounts = [{"name": "proj", "source": str(root)}]

    assert sm.is_in_mount_source(str(root / "a.txt"), mounts) is True
    assert sm.is_in_mount_source(str(tmp_path / "proj2" / "a.txt"), mounts) is False


def test_container_mounts_skip_missing_sources(tmp_path):
    existing = tmp_path / "ok"
    existing.mkdir()
    mounts = [
        {"name": "ok", "source": str(existing)},
        {"name": "gone", "source": str(tmp_path / "gone")},
    ]

    assert sm.container_mounts(mounts) == [
        {
            "name": "ok",
            "source": str(existing),
            "destination": "/mount/ok",
        }
    ]


def test_mounts_prompt_lines_list_container_mapping(tmp_path):
    root = tmp_path / "ok"
    root.mkdir()
    mounts = [{"name": "ok", "source": str(root)}]

    assert sm.mounts_prompt_lines(mounts) == [f"/mount/ok -> {root}"]


def test_save_and_load_roundtrip_dedupes_sources(mount_cfg, tmp_path):
    root = tmp_path / "a"
    root.mkdir()

    assert sm.save_mounts(
        [
            {"name": "a", "source": str(root)},
            {"name": "A", "source": str(root)},
        ]
    )
    assert sm.load_mounts() == [{"name": "a", "source": str(root)}]
    assert json.loads(mount_cfg.read_text(encoding="utf-8"))["mounts"][0]["name"] == "a"


def test_add_mount_auto_suffixes_duplicate_folder_names(mount_cfg, tmp_path):
    first = tmp_path / "x" / "src"
    second = tmp_path / "y" / "src"
    first.mkdir(parents=True)
    second.mkdir(parents=True)

    assert sm.add_mount(str(first))["name"] == "src"
    assert sm.add_mount(str(second))["name"] == "src-2"
    assert [m["name"] for m in sm.load_mounts()] == ["src", "src-2"]


def test_rename_mount_rejects_taken_name(mount_cfg, tmp_path):
    first = tmp_path / "a"
    second = tmp_path / "b"
    first.mkdir()
    second.mkdir()
    sm.save_mounts(
        [
            {"name": "a", "source": str(first)},
            {"name": "b", "source": str(second)},
        ]
    )

    with pytest.raises(sm.MountError):
        sm.rename_mount("a", "B")
    assert sm.rename_mount("a", "c")["name"] == "c"


def test_remove_mount_raises_for_unknown_name(mount_cfg, tmp_path):
    root = tmp_path / "a"
    root.mkdir()
    sm.save_mounts([{"name": "a", "source": str(root)}])

    with pytest.raises(sm.MountError):
        sm.remove_mount("missing")
    assert sm.remove_mount("a")
    assert sm.load_mounts() == []


def test_system_info_lists_available_mounts(mount_cfg, tmp_path):
    """SPEC-045 AC-6：@SYS 列出容器路径与宿主路径的对应关系。"""
    from src.agent import hook_paths

    root = tmp_path / "proj"
    root.mkdir()
    sm.save_mounts([{"name": "proj", "source": str(root)}])

    info = hook_paths.get_system_info(str(tmp_path / "agent_vm"))

    assert f"/mount/proj -> {root}" in info
