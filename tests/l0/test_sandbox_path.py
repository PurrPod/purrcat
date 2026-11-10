"""沙盒路径映射：Agent 视角 /agent_vm 到宿主机真实目录。"""

from __future__ import annotations

import os
from pathlib import Path

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
