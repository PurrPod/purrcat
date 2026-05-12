import os
import shutil
from fastapi import APIRouter, HTTPException
from src.utils.config import DATA_DIR
from tui.api import get_task_list, format_task_log

# 创建 Tasks 专属路由器
router = APIRouter(prefix="/api/tasks", tags=["Tasks"])

@router.get("")
def list_tasks():
    """获取所有任务列表"""
    return get_task_list()

@router.get("/{task_id}/log")
def get_task_log(task_id: str):
    """获取具体任务格式化后的日志"""
    log_content = format_task_log(task_id)
    return {
        "task_id": task_id,
        "log": log_content
    }

@router.delete("/{task_id}")
def delete_task(task_id: str):
    """删除指定的任务记录 (清除对应文件夹并停止进程)"""
    # 1. 删除磁盘上的任务文件夹
    task_dir = os.path.join(DATA_DIR, "checkpoints", "task", task_id)
    if os.path.exists(task_dir):
        try:
            shutil.rmtree(task_dir)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to delete task folder: {e}")
            
    # 2. 从内存中踢除该任务实例 (如果还在运行)
    try:
        from src.harness.process import TASK_INSTANCES
        if task_id in TASK_INSTANCES:
            TASK_INSTANCES[task_id].state = "killed"
            del TASK_INSTANCES[task_id]
    except Exception as e:
        print(f"⚠️ 内存任务清理失败 (可能任务已结束): {e}")

    return {"status": "ok", "message": f"Task {task_id} successfully deleted."}