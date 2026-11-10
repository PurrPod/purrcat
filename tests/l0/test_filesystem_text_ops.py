"""文件工具纯函数边界（SPEC-016 AC-7）。"""

from __future__ import annotations

import os

import pytest

from src.tool.filesystem import _shared
from src.tool.filesystem.exceptions import FileSystemError


def test_normalize_newlines_collapses_crlf_and_cr():
    """SPEC-016 AC-7：匹配与替换统一在 \\n 口径。"""
    assert _shared.normalize_newlines("a\r\nb\rc\n") == "a\nb\nc\n"


def test_detect_dominant_newline():
    """SPEC-016 AC-7：主导行尾为 CRLF 时写回 CRLF，否则 LF。"""
    assert _shared.detect_dominant_newline(b"a\r\nb\r\nc\n") == "\r\n"
    assert _shared.detect_dominant_newline(b"a\nb\nc\r\n") == "\n"
    assert _shared.detect_dominant_newline(b"") == "\n"


def test_apply_newline_style_only_rewrites_lf():
    """SPEC-016 AC-7：仅当主导行尾不是 LF 时替换，避免二次污染。"""
    assert _shared.apply_newline_style("a\nb", "\n") == "a\nb"
    assert _shared.apply_newline_style("a\nb", "\r\n") == "a\r\nb"


def test_build_lock_path_is_stable_and_collision_free(tmp_path):
    """SPEC-016 AC-7：同一路径生成同一锁文件，不同路径不冲突。"""
    lock_dir = str(tmp_path)
    first = _shared.build_lock_path(os.path.join("a", "b.txt"), lock_dir)
    second = _shared.build_lock_path(os.path.join("a", "b.txt"), lock_dir)
    other = _shared.build_lock_path(os.path.join("a", "c.txt"), lock_dir)

    assert first == second
    assert first != other
    assert first.endswith(".lock")
    assert ":" not in os.path.basename(first)


def test_atomic_write_text_replaces_content_without_temp_leftovers(tmp_path):
    """SPEC-016 AC-7：原子写入覆盖旧内容并清理临时文件。"""
    target = tmp_path / "note.txt"
    target.write_text("old", encoding="utf-8")

    _shared.atomic_write_text(str(target), "new\r\nline")

    assert target.read_bytes() == b"new\r\nline"
    assert [p.name for p in tmp_path.iterdir()] == ["note.txt"]


def test_build_diff_uses_sandbox_style_path(tmp_path):
    """SPEC-016 AC-7：diff 头使用以 / 开头的展示路径，而非 basename。"""
    diff = _shared.build_diff("old\n", "new\n", "agent_vm/a.txt")

    assert "--- a/agent_vm/a.txt" in diff
    assert "+++ b/agent_vm/a.txt" in diff
    assert "-old" in diff
    assert "+new" in diff


def test_summarize_diff_counts_added_and_removed_lines():
    """SPEC-016 AC-7：diff 摘要只统计内容行，不统计文件头。"""
    diff = "--- a/x\n+++ b/x\n@@ -1 +1 @@\n-old\n+new\n+more\n"

    assert _shared.summarize_diff(diff) == "新增了 2 行代码，删除了 1 行代码"
    assert _shared.summarize_diff("") == "新增 0 行，删除 0 行"


def test_select_line_window_clamps_bounds():
    """SPEC-016 AC-7：读取窗口起点不为负，终点不超过总行数。"""
    lines = ["0\n", "1\n", "2\n"]

    assert _shared.select_line_window(lines, -5, 2) == (0, 2)
    assert _shared.select_line_window(lines, 2, 99) == (2, 3)
    assert _shared.select_line_window([], 0, 10) == (0, 0)


def test_replace_occurrences_rejects_missing_and_ambiguous():
    """SPEC-016 AC-7：找不到或多次命中时保持原有报错语义。"""
    with pytest.raises(FileSystemError, match="未找到"):
        _shared.replace_occurrences("abc", "x", "y", replace_all=False)

    with pytest.raises(FileSystemError, match="出现了 2 次"):
        _shared.replace_occurrences("a a", "a", "b", replace_all=False)


def test_replace_occurrences_replace_all_and_single():
    """SPEC-016 AC-7：replace_all 与首个命中替换的返回值一致。"""
    assert _shared.replace_occurrences("a a", "a", "b", replace_all=True) == (
        "b b",
        2,
    )
    assert _shared.replace_occurrences("x a y", "a", "b", replace_all=False) == (
        "x b y",
        1,
    )
