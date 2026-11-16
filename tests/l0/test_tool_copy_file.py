"""copy 覆盖与 undo 回溯（SPEC-029）。"""

from __future__ import annotations

import pytest

from src.tool.filesystem import history
from src.tool.filesystem.copy_file import copy_file
from src.tool.filesystem.exceptions import FileSystemError
from src.tool.filesystem.history import rewind_file


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """放行全部读写权限，并把时光机目录指到 tmp，避免碰真实 ~/.purrcat。"""
    monkeypatch.setattr(
        "src.utils.config.get_file_config",
        lambda: {
            "default_permission": "readwrite",
            "permissions": {"blocked": [], "readonly": [], "writable": []},
        },
    )
    monkeypatch.setattr(history, "HISTORY_DIR", str(tmp_path / "history"))
    return tmp_path


def test_copy_overwrites_file_reports_and_undo_restores(sandbox):
    src = sandbox / "src.txt"
    dst = sandbox / "dst.txt"
    src.write_text("new", encoding="utf-8")
    dst.write_text("old", encoding="utf-8")

    result = copy_file(str(src), str(dst))

    assert result["overwritten"] is True
    assert dst.read_text(encoding="utf-8") == "new"
    assert "覆盖" in result["message"]
    assert "undo" in result["message"]

    rewind_file(str(dst))
    assert dst.read_text(encoding="utf-8") == "old"


def test_copy_into_dir_backs_up_shadowed_inner_file(sandbox):
    src = sandbox / "src.txt"
    dst_dir = sandbox / "dir"
    src.write_text("new", encoding="utf-8")
    dst_dir.mkdir()
    (dst_dir / "src.txt").write_text("old", encoding="utf-8")
    (dst_dir / "keep.txt").write_text("keep", encoding="utf-8")

    result = copy_file(str(src), str(dst_dir))

    assert result["overwritten"] is True
    assert (dst_dir / "src.txt").read_text(encoding="utf-8") == "new"
    assert (dst_dir / "keep.txt").read_text(encoding="utf-8") == "keep"

    rewind_file(str(dst_dir / "src.txt"))
    assert (dst_dir / "src.txt").read_text(encoding="utf-8") == "old"


def test_copy_dir_merge_overwrites_and_keeps_extra_files(sandbox):
    src_dir = sandbox / "src"
    dst_dir = sandbox / "dst"
    src_dir.mkdir()
    dst_dir.mkdir()
    (src_dir / "a.txt").write_text("new-a", encoding="utf-8")
    (src_dir / "b.txt").write_text("new-b", encoding="utf-8")
    (dst_dir / "a.txt").write_text("old-a", encoding="utf-8")
    (dst_dir / "c.txt").write_text("keep-c", encoding="utf-8")

    result = copy_file(str(src_dir), str(dst_dir))

    assert result["overwritten"] is True
    assert (dst_dir / "a.txt").read_text(encoding="utf-8") == "new-a"
    assert (dst_dir / "b.txt").read_text(encoding="utf-8") == "new-b"
    assert (dst_dir / "c.txt").read_text(encoding="utf-8") == "keep-c"

    rewind_file(str(dst_dir / "a.txt"))
    assert (dst_dir / "a.txt").read_text(encoding="utf-8") == "old-a"


def test_copy_dir_onto_file_still_rejected(sandbox):
    src_dir = sandbox / "src"
    dst = sandbox / "dst.txt"
    src_dir.mkdir()
    dst.write_text("old", encoding="utf-8")

    with pytest.raises(FileSystemError):
        copy_file(str(src_dir), str(dst))
    assert dst.read_text(encoding="utf-8") == "old"


def test_copy_to_fresh_target_reports_no_overwrite(sandbox):
    src = sandbox / "src.txt"
    dst = sandbox / "sub" / "dst.txt"
    src.write_text("new", encoding="utf-8")

    result = copy_file(str(src), str(dst))

    assert result["overwritten"] is False
    assert "覆盖" not in result["message"]
    assert dst.read_text(encoding="utf-8") == "new"
