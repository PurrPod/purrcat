import os
import traceback
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# 直接引入纯粹的路径映射函数，避开 require_write 的大模型权限沙盒
from src.tool.filesystem.utils import resolve_absolute_path
from src.tool.filesystem.history import (
    rewind_file_by_id,
    ack_backup,
    get_valid_backup_ids,
    HISTORY_DIR,
    get_all_diffs,
)

router = APIRouter(prefix="/api/filesystem", tags=["UI Direct File Access"])


class UIRollbackReq(BaseModel):
    path: str
    backup_id: str


@router.get("/history_list")
def get_history_list():
    """直接读取 .agent_history 目录，返回真实存在的备份文件列表"""
    if not os.path.exists(HISTORY_DIR):
        return []

    files = os.listdir(HISTORY_DIR)
    history_list = []

    for f in files:
        if f.endswith(".empty"):
            continue

        # 解析文件名：safe_path@backup_id
        parts = f.rsplit("@", 1)
        if len(parts) != 2:
            continue

        safe_path_part = parts[0]
        backup_id = parts[1]

        # 还原原始路径格式
        original_path = safe_path_part.replace("%", os.sep)
        # 添加 / 前缀使其成为沙盒路径
        sandbox_path = "/" + original_path

        history_list.append(
            {
                "id": f,  # 使用完整文件名作为唯一ID
                "path": sandbox_path,
                "backup_id": backup_id,
                "time": "",  # 时间戳可自行转换
            }
        )

    return history_list


@router.get("/backups")
def api_get_valid_backups():
    """提供给前端：校验哪些快照还在硬盘上存活"""
    try:
        ids = get_valid_backup_ids()
        return {"status": "success", "valid_ids": ids}
    except Exception:
        traceback.print_exc()
        return {"status": "error", "valid_ids": []}


@router.post("/undo")
def ui_undo_action(req: UIRollbackReq):
    """提供给前端 UI 的一键回滚（最高权限）"""
    try:
        resolved_path = resolve_absolute_path(req.path)
        result_msg = rewind_file_by_id(resolved_path, req.backup_id)
        return {"status": "success", "message": result_msg}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"回滚失败: {str(e)}")


@router.post("/ack")
def ui_ack_action(req: UIRollbackReq):
    """用户确认更改，删除磁盘备份，解决空间膨胀"""
    try:
        resolved_path = resolve_absolute_path(req.path)
        ack_backup(resolved_path, req.backup_id)
        return {"status": "success"}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"清理备份失败: {str(e)}")


@router.get("/diffs")
def api_get_global_diffs():
    """🌟 新增：提供给前端全局读取所有未确认的代码变更 (DiffView)"""
    try:
        diffs = get_all_diffs()
        return {"status": "success", "diffs": diffs}
    except Exception:
        traceback.print_exc()
        return {"status": "error", "diffs": []}
