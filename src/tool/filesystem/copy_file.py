import os
import shutil

from src.tool.filesystem.exceptions import FileSystemError, HostPathNotFoundError
from src.tool.filesystem.utils import require_read, require_write


def copy_file(path_from: str, path_to: str) -> dict:
    """Copy 工具：安全的文件与目录复制 (带有防覆盖保护)"""
    if not path_from or not path_to:
        raise FileSystemError("copy 操作必须同时提供 path_from 和 path_to。")

    src_path = require_read(path_from)
    dst_path = require_write(path_to)

    if not os.path.exists(src_path):
        raise HostPathNotFoundError(src_path)

    if src_path == dst_path:
        raise FileSystemError("源路径和目标路径相同，无需复制。")

    if os.path.exists(dst_path):
        raise FileSystemError(
            f"⚠️ 复制失败: 目标路径已存在文件或目录 '{os.path.basename(dst_path)}'。\n"
            "安全策略拦截：禁止复制操作覆盖已有文件。\n"
            "解决：请为 path_to 提供一个新的文件名或路径。"
        )

    # 自动创建目标目录的父级目录
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)

    try:
        if os.path.isdir(src_path):
            shutil.copytree(src_path, dst_path)
            type_str = "目录"
        else:
            shutil.copy2(src_path, dst_path)
            type_str = "文件"
    except Exception as e:
        raise FileSystemError(f"{type_str}复制失败: {str(e)}")

    return {
        "path_from": src_path,
        "path_to": dst_path,
        "message": f"成功将{type_str} {os.path.basename(src_path)} 复制为 {os.path.basename(dst_path)}",
    }
