import os
import difflib

from src.tool.filesystem.exceptions import FileSystemError, HostPathNotFoundError
from src.tool.filesystem.utils import require_write
from src.tool.filesystem.history import track_edit, save_backup_meta


def delete_file(path: str) -> dict:
    """Delete 工具：安全的软删除 (仅限文件，支持 undo 和 UI Diff 渲染)"""
    if not path:
        raise FileSystemError("delete 操作必须提供 path 参数。")

    target_path = require_write(path)

    if not os.path.exists(target_path):
        raise HostPathNotFoundError(target_path)

    if os.path.isdir(target_path):
        raise FileSystemError(
            "⚠️ 安全策略拦截：为防止大规模误删，Agent 仅被允许删除【单个文件】。\n"
            "如需清理目录，请逐个删除文件，或请求人类协助。"
        )

    # 1. 在物理删除前，先读取文件的旧内容用于计算 Diff
    old_content = ""
    try:
        with open(target_path, "r", encoding="utf-8") as f:
            old_content = f.read()
    except UnicodeDecodeError:
        old_content = "[二进制文件或富文本，已被删除]\n"
    except Exception:
        pass

    # 2. 触发时光机物理备份，并执行删除
    try:
        backup_id = track_edit(target_path)
        os.remove(target_path)
    except Exception as e:
        raise FileSystemError(f"删除失败: {str(e)}")

    # 3. 核心修复：计算 Diff（用旧内容对比一个空数组），并写入 Meta 文件
    format_path = path if path.startswith("/") else "/" + path
    diff_lines = list(
        difflib.unified_diff(
            old_content.splitlines(keepends=True),
            [],  # 目标为空，制造出全量删除的 Diff 效果
            fromfile=f"a{format_path}",
            tofile=f"b{format_path}",
            n=3,
        )
    )
    diff_text = "".join(diff_lines)
    
    # 写入 .meta，前端立刻就能捕捉到
    save_backup_meta(target_path, backup_id, diff_text)

    return {
        "path": target_path,
        "backup_id": backup_id,
        "message": f"🗑️ 成功删除文件 {os.path.basename(target_path)}。\n💡 已自动备份至时光机，用户可在 File Changes 窗口核对或回滚！",
        "diff": diff_text
    }