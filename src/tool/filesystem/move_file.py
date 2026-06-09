import os
import shutil

from src.tool.filesystem.exceptions import FileSystemError, HostPathNotFoundError
from src.tool.filesystem.utils import require_write


def move_file(path_from: str, path_to: str) -> dict:
    """Move 工具：安全的文件移动与重命名 (带防覆盖锁)"""
    if not path_from or not path_to:
        raise FileSystemError("move 操作必须同时提供 path_from 和 path_to。")

    src_path = require_write(path_from)
    dst_path = require_write(path_to)

    if not os.path.exists(src_path):
        raise HostPathNotFoundError(src_path)

    if src_path == dst_path:
        raise FileSystemError("源路径和目标路径相同，无需移动。")

    if os.path.exists(dst_path):
        raise FileSystemError(
            f"⚠️ 移动失败: 目标路径已存在文件或目录 '{os.path.basename(dst_path)}'。\n"
            "安全策略拦截：禁止移动操作覆盖已有文件，以防数据丢失。\n"
            "解决：请为 path_to 提供一个新的文件名或路径。"
        )

    os.makedirs(os.path.dirname(dst_path), exist_ok=True)

    try:
        shutil.move(src_path, dst_path)
    except Exception as e:
        raise FileSystemError(f"文件移动失败: {str(e)}")

    return {
        "path_from": src_path,
        "path_to": dst_path,
        "message": f"成功将 {os.path.basename(src_path)} 移动/重命名为 {os.path.basename(dst_path)}",
    }
