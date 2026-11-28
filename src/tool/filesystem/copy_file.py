import os
import shutil

from src.tool.filesystem import _shared
from src.tool.filesystem.exceptions import FileSystemError, HostPathNotFoundError
from src.tool.filesystem.history import track_edit, save_backup_meta
from src.tool.filesystem.utils import require_read, require_write

_UNDO_HINT = "提示：如需恢复覆盖前的内容，可对被覆盖路径使用 `action='undo'` 回溯。"


def _backup_single_file(target_path: str):
    """覆盖前备份单个目标文件并写入 meta，保证可独立 undo。"""
    backup_id = track_edit(target_path)
    format_path = _shared.format_diff_path(target_path)
    diff_text = (
        f"--- a{format_path}\n+++ b{format_path}\n"
        f"@@ -1 +1 @@\n- [copy 覆盖前的内容，已备份可 undo]\n"
    )
    save_backup_meta(target_path, backup_id, diff_text)


def _backup_merge_overwrites(src_dir: str, dst_dir: str) -> int:
    """目录合并覆盖前，逐个备份将被同名覆盖的目标文件。返回备份文件数。"""
    count = 0
    for root, _dirs, files in os.walk(src_dir):
        rel_root = os.path.relpath(root, src_dir)
        dst_root = dst_dir if rel_root == "." else os.path.join(dst_dir, rel_root)
        for name in files:
            dst_file = os.path.join(dst_root, name)
            if os.path.isfile(dst_file):
                _backup_single_file(dst_file)
                count += 1
    return count


def _backup_before_overwrite(src_path: str, dst_path: str) -> str:
    """覆盖前备份目标位置已有内容；返回覆盖描述文案（未覆盖返回空串）。"""
    if not os.path.exists(dst_path):
        return ""

    if os.path.isdir(dst_path):
        if os.path.isdir(src_path):
            count = _backup_merge_overwrites(src_path, dst_path)
            return (
                f"目录 {os.path.basename(dst_path)}（合并覆盖其中 {count} 个同名文件）"
            )
        # 文件已存在目录：copy2 会复制进目录，实际被覆盖的是同名文件
        target = os.path.join(dst_path, os.path.basename(src_path))
        if os.path.isfile(target):
            _backup_single_file(target)
            return f"目录内同名文件 {os.path.basename(target)}"
        return ""

    if os.path.isdir(src_path):
        raise FileSystemError(
            f"复制失败: 目标位置 '{os.path.basename(dst_path)}' 已是文件，无法将目录复制到文件位置。\n"
            "解决：请为 path_to 提供一个新的目录路径。"
        )

    _backup_single_file(dst_path)
    return f"文件 {os.path.basename(dst_path)}"


def copy_file(path_from: str, path_to: str) -> dict:
    """Copy 工具：文件与目录复制（目标可写即允许覆盖，覆盖前自动备份支持 undo）"""
    if not path_from or not path_to:
        raise FileSystemError("copy 操作必须同时提供 path_from 和 path_to。")

    src_path = require_read(path_from)
    dst_path = require_write(path_to)

    if not os.path.exists(src_path):
        raise HostPathNotFoundError(src_path)

    if src_path == dst_path:
        raise FileSystemError("源路径和目标路径相同，无需复制。")

    overwritten = _backup_before_overwrite(src_path, dst_path)

    # 自动创建目标目录的父级目录
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)

    try:
        if os.path.isdir(src_path):
            shutil.copytree(src_path, dst_path, dirs_exist_ok=True)
            type_str = "目录"
        else:
            shutil.copy2(src_path, dst_path)
            type_str = "文件"
    except Exception as e:
        raise FileSystemError(f"{type_str}复制失败: {str(e)}")

    message = f"成功将{type_str} {os.path.basename(src_path)} 复制为 {os.path.basename(dst_path)}"
    if overwritten:
        message = f"已覆盖：{overwritten}\n{message}\n{_UNDO_HINT}"

    return {
        "path_from": src_path,
        "path_to": dst_path,
        "overwritten": bool(overwritten),
        "message": message,
    }
