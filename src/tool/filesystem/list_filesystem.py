"""文件系统列表功能 - 列出宿主机文件系统结构"""

import os
import time

from src.tool.filesystem.exceptions import HostPathNotFoundError
from src.tool.filesystem.utils import is_readable, require_read


def list_filesystem(path: str = ".", depth: int = 1, show_hidden: bool = False) -> dict:
    """
    列出宿主机文件系统结构（带大小、绝对路径），遵循权限规则

    Args:
        path: 起始路径，默认当前目录
        depth: 递归深度，1=仅当前目录，2=子目录，以此类推
        show_hidden: 是否显示隐藏文件/目录

    Returns:
        包含 path, tree, dir_count, file_count, total_size_bytes, total_size_mb 的字典
    """
    root = require_read(path)

    if not os.path.exists(root):
        raise HostPathNotFoundError(root)

    lines = []
    total_size = 0
    file_count = 0
    dir_count = 0

    def _walk(current: str, prefix: str, remaining_depth: int):
        nonlocal total_size, file_count, dir_count

        if not is_readable(current):
            lines.append(f"{prefix}[权限不足，已跳过]")
            return

        try:
            entries = sorted(os.listdir(current))
        except PermissionError:
            lines.append(f"{prefix}[权限不足]")
            return

        for i, entry in enumerate(entries):
            if not show_hidden and entry.startswith("."):
                continue

            full_path = os.path.join(current, entry)
            is_last = i == len(entries) - 1
            connector = "└── " if is_last else "├── "

            try:
                stat = os.stat(full_path)
                is_dir = os.path.isdir(full_path)
                size = stat.st_size
                mtime = time.strftime("%m-%d %H:%M", time.localtime(stat.st_mtime))

                if is_dir:
                    dir_count += 1
                    size_str = ""
                    lines.append(f"{prefix}{connector}{entry}/  ({mtime})")
                    if remaining_depth > 1:
                        ext = "    " if is_last else "│   "
                        _walk(full_path, prefix + ext, remaining_depth - 1)
                else:
                    file_count += 1
                    total_size += size
                    if size < 1024:
                        size_str = f"{size}B"
                    elif size < 1024 * 1024:
                        size_str = f"{size / 1024:.1f}KB"
                    else:
                        size_str = f"{size / 1024 / 1024:.1f}MB"
                    lines.append(f"{prefix}{connector}{entry}  ({size_str}, {mtime})")
            except (OSError, PermissionError):
                lines.append(f"{prefix}{connector}{entry}  [不可访问]")

    root_stat = os.stat(root)
    root_mtime = time.strftime("%Y-%m-%d %H:%M", time.localtime(root_stat.st_mtime))
    lines.append(f"{root}  ({root_mtime})")

    _walk(root, "", depth + 1)

    summary = (
        f"\n📁 {dir_count} 个目录, 📄 {file_count} 个文件, "
        f"总计 {total_size / 1024 / 1024:.1f}MB"
    )
    lines.append(summary)

    return {
        "path": root,
        "tree": "\n".join(lines),
        "dir_count": dir_count,
        "file_count": file_count,
        "total_size_bytes": total_size,
        "total_size_mb": round(total_size / 1024 / 1024, 1),
    }
