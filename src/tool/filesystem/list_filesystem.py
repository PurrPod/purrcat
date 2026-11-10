"""文件系统列表功能 - 真正的 ls：仅列出单层目录内容（含元数据）"""

import os
import time

from src.tool.filesystem.exceptions import HostPathNotFoundError, PermissionDeniedError
from src.tool.filesystem.utils import require_read
from src.utils._format import human_bytes_ls


def _format_entry_line(name: str, full_path: str) -> tuple[str, bool]:
    """
    格式化单个条目为 ls 风格的一行：类型 大小 修改时间 名称
    返回 (行文本, 是否目录)；stat 失败时标记不可访问
    """
    try:
        st = os.lstat(full_path)
        mtime = time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime))

        if os.path.islink(full_path):
            try:
                target = os.readlink(full_path)
            except OSError:
                target = "?"
            return (
                f"l    {human_bytes_ls(st.st_size):>10}  {mtime}  {name} -> {target}",
                False,
            )

        if os.path.isdir(full_path):
            return f"d    {'-':>10}  {mtime}  {name}/", True

        return f"-    {human_bytes_ls(st.st_size):>10}  {mtime}  {name}", False
    except (OSError, PermissionError):
        return f"?    {'-':>10}  {'-':>16}  {name}  [不可访问]", False


def list_filesystem(path: str = ".") -> dict:
    """
    列出目录单层内容（ls 风格：类型、大小、修改时间），遵循权限规则。
    不递归，如需查看子目录请再次调用并指定该子目录路径。

    Args:
        path: 目标目录（或单个文件）路径

    Returns:
        包含 path, tree, dir_count, file_count 的字典
    """
    root = require_read(path)

    if not os.path.exists(root):
        raise HostPathNotFoundError(root)

    # ls 对单个文件直接展示该文件自身的元数据
    if not os.path.isdir(root):
        line, _ = _format_entry_line(os.path.basename(root) or root, root)
        return {"path": root, "tree": line, "dir_count": 0, "file_count": 1}

    try:
        names = sorted(os.listdir(root), key=str.lower)
    except PermissionError:
        raise PermissionDeniedError(root, "无权限读取该目录内容")

    lines = [f"{root}/"]
    dir_count = 0
    file_count = 0

    for name in names:
        line, is_dir = _format_entry_line(name, os.path.join(root, name))
        if is_dir:
            dir_count += 1
        else:
            file_count += 1
        lines.append(line)

    return {
        "path": root,
        "tree": "\n".join(lines),
        "dir_count": dir_count,
        "file_count": file_count,
    }
