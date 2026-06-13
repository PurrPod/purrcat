import os

from src.tool.filesystem.exceptions import FileSystemError, HostPathNotFoundError
from src.tool.filesystem.utils import require_write
from src.tool.filesystem.history import track_edit


def delete_file(path: str) -> dict:
    """Delete 工具：安全的软删除 (仅限文件，支持 undo)"""
    if not path:
        raise FileSystemError("delete 操作必须提供 path 参数。")

    # 1. 权限校验：必须拥有 writable 权限才能删除
    target_path = require_write(path)

    if not os.path.exists(target_path):
        raise HostPathNotFoundError(target_path)

    # 2. 灾难防护：禁止大模型直接删除整个目录！
    if os.path.isdir(target_path):
        raise FileSystemError(
            "⚠️ 安全策略拦截：为防止大规模误删，Agent 仅被允许删除【单个文件】。\n"
            "如需清理目录，请逐个删除文件，或请求人类协助。"
        )

    # 3. 核心：执行软删除前先进入 history 备份体系
    try:
        backup_id = track_edit(target_path)
        os.remove(target_path)
    except Exception as e:
        raise FileSystemError(f"删除失败: {str(e)}")

    return {
        "path": target_path,
        "backup_id": backup_id,
        "message": f"🗑️ 成功删除文件 {os.path.basename(target_path)}。\n💡 已自动备份至时光机，如系误删请立即执行 undo 操作恢复！",
    }
