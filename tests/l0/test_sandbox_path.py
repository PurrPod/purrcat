"""沙盒路径映射：Agent 视角 /agent_vm 到宿主机真实目录。"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from src.agent import hook_handler as hook_mod
from src.agent.hook_handler import HookHandler
from src.utils import path as sandbox_path


def test_maps_agent_vm_prefix_to_host_dir(tmp_path, monkeypatch):
    root = tmp_path / "agent_vm"
    monkeypatch.setattr(sandbox_path, "AGENT_VM_DIR", str(root))

    result = sandbox_path.convert_sandbox_path("/agent_vm/projects/a.txt")

    assert Path(result) == (root / "projects" / "a.txt").resolve()


def test_tolerates_double_slash_from_url_parsing(tmp_path, monkeypatch):
    root = tmp_path / "agent_vm"
    monkeypatch.setattr(sandbox_path, "AGENT_VM_DIR", str(root))

    assert sandbox_path.convert_sandbox_path("//agent_vm/a.txt") == str(
        (root / "a.txt").resolve()
    )


def test_maps_bare_agent_vm_root(tmp_path, monkeypatch):
    root = tmp_path / "agent_vm"
    monkeypatch.setattr(sandbox_path, "AGENT_VM_DIR", str(root))

    assert sandbox_path.convert_sandbox_path("/agent_vm") == str(root)


def test_normalizes_backslashes(tmp_path, monkeypatch):
    root = tmp_path / "agent_vm"
    monkeypatch.setattr(sandbox_path, "AGENT_VM_DIR", str(root))

    assert sandbox_path.convert_sandbox_path(r"\agent_vm\a.txt") == str(
        (root / "a.txt").resolve()
    )


def test_other_paths_are_only_absolutized(tmp_path):
    assert sandbox_path.convert_sandbox_path("relative/a.txt") == os.path.abspath(
        "relative/a.txt"
    )
    assert sandbox_path.convert_sandbox_path(str(tmp_path / "a.txt")) == str(
        tmp_path / "a.txt"
    )


def test_maps_mount_alias_to_host_dir(tmp_path, monkeypatch):
    """SPEC-045 AC-1：/mount/<别名> 按挂载配置映射回宿主路径。"""
    from src.utils import sandbox_mounts

    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    cfg = tmp_path / "mounts.json"
    cfg.write_text(
        json.dumps({"mounts": [{"name": "proj", "source": str(root)}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(sandbox_mounts, "MOUNTS_CONFIG_PATH", str(cfg))

    result = sandbox_path.convert_sandbox_path("/mount/proj/src/a.txt")

    assert Path(result) == (root / "src" / "a.txt").resolve()


def _hook_path(tmp_path, monkeypatch, path):
    root = tmp_path / "vm"
    monkeypatch.setattr(hook_mod, "AGENT_VM_DIR", str(root))
    return HookHandler(config_dict={"hooks": {}})._resolve_path(path), root


def test_hook_maps_sandbox_absolute_path(tmp_path, monkeypatch):
    result, root = _hook_path(tmp_path, monkeypatch, "/agent_vm/projects/a.txt")

    assert Path(result) == root / "projects" / "a.txt"


def test_hook_maps_sandbox_relative_path(tmp_path, monkeypatch):
    result, root = _hook_path(tmp_path, monkeypatch, "agent_vm/projects/a.txt")

    assert Path(result) == root / "projects" / "a.txt"


@pytest.mark.parametrize("path", ["/agent_vm", "agent_vm"])
def test_hook_maps_bare_sandbox_root(tmp_path, monkeypatch, path):
    result, root = _hook_path(tmp_path, monkeypatch, path)

    assert Path(result) == root


@pytest.mark.parametrize("path", ["/agent_vm_backup/a.txt", "agent_vm_backup/a.txt"])
def test_hook_ignores_lookalike_prefix(tmp_path, monkeypatch, path):
    result, _ = _hook_path(tmp_path, monkeypatch, path)

    assert result == path
