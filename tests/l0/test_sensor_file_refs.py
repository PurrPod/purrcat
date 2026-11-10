"""Sensor 出向文件引用解析（SPEC-011）。"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.sensor import file_refs
from src.utils import path as sandbox_path


@pytest.fixture
def agent_vm(tmp_path, monkeypatch):
    root = tmp_path / "agent_vm"
    root.mkdir()
    monkeypatch.setattr(sandbox_path, "AGENT_VM_DIR", str(root))
    return root


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("/agent_vm/a.txt", "/agent_vm/a.txt"),
        ("./agent_vm/a.txt", "/agent_vm/a.txt"),
        ("../agent_vm/a.txt", "/agent_vm/a.txt"),
        ("agent_vm/a.txt", "/agent_vm/a.txt"),
        ("file:///agent_vm/a.txt", "/agent_vm/a.txt"),
        ("/agent_vm/a.txt，", "/agent_vm/a.txt"),
        ("/agent_vm/a.txt).", "/agent_vm/a.txt"),
        ("C:\\tmp\\a.txt", "C:\\tmp\\a.txt"),
    ],
)
def test_normalize_candidate_accepts_known_forms(raw, expected):
    assert file_refs.normalize_candidate(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "file://host/share/a.txt",
        "/tmp/a.txt",
        "agent_vm_backup/a.txt",
        "https://example.com/a.txt",
    ],
)
def test_normalize_candidate_rejects_other_forms(raw):
    assert file_refs.normalize_candidate(raw) is None


def test_extract_reads_markdown_link_and_dedupes(agent_vm):
    target = agent_vm / "report.png"
    target.write_text("x", encoding="utf-8")

    text = "见 ![报告](/agent_vm/report.png)，也可 [下载](./agent_vm/report.png)"

    assert file_refs.extract_file_paths(text) == [str(target)]


def test_extract_reads_bare_path_and_skips_missing(agent_vm):
    existing = agent_vm / "a.txt"
    existing.write_text("x", encoding="utf-8")

    text = "文件 /agent_vm/a.txt 与 /agent_vm/missing.txt"

    assert file_refs.extract_file_paths(text) == [str(existing)]


def test_extract_ignores_non_file_targets(agent_vm):
    (agent_vm / "dir").mkdir()

    text = "/agent_vm/dir https://example.com/a.txt"

    assert file_refs.extract_file_paths(text) == []


@pytest.mark.skipif(os.name != "nt", reason="盘符路径只在 Windows 具有绝对路径语义")
def test_extract_accepts_windows_absolute_path(tmp_path):
    target = tmp_path / "win.txt"
    target.write_text("x", encoding="utf-8")

    assert file_refs.extract_file_paths(str(target)) == [str(target)]


def test_bridge_reexports_extract_file_paths():
    from src.sensor.bridge import extract_file_paths

    assert extract_file_paths is file_refs.extract_file_paths


def test_extract_returns_host_paths(agent_vm):
    nested = agent_vm / "sub"
    nested.mkdir()
    target = nested / "deep.txt"
    target.write_text("x", encoding="utf-8")

    result = file_refs.extract_file_paths("路径：/agent_vm/sub/deep.txt")

    assert Path(result[0]) == target
    assert result[0].startswith(str(agent_vm))
