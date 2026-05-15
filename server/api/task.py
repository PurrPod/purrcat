import os
import json
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from src.utils.task_api import (
    get_task_list,
    get_task_state,
    kill_task,
    submit_instruction,
    delete_task,
    force_push_task,
)
from src.utils.log_api import get_task_log_structured
from src.utils.task_api import get_task_log_jsonl

router = APIRouter(prefix="/api/tasks", tags=["Tasks"])


class SubmitInstructionRequest(BaseModel):
    node_id: str
    content: str


@router.get("")
def list_tasks():
    return get_task_list()


@router.get("/{task_id}/log")
def get_task_log(task_id: str):
    from src.harness.process import TASK_INSTANCES
    from src.utils.config import DATA_DIR

    # 1. 寻找日志目录
    checkpoint_dir = None
    task_instance = TASK_INSTANCES.get(task_id)
    if task_instance and hasattr(task_instance, "checkpoint_dir"):
        checkpoint_dir = task_instance.checkpoint_dir
    else:
        base_dir = os.path.join(DATA_DIR, "checkpoints", "task")
        if os.path.isdir(base_dir):
            for entry in os.listdir(base_dir):
                if task_id in entry:
                    checkpoint_dir = os.path.join(base_dir, entry)
                    break

    if not checkpoint_dir:
        return {"task_id": task_id, "grouped_logs": {}}

    log_path = os.path.join(checkpoint_dir, "log.jsonl")
    grouped_logs = {"system": []}  # 兜底分组

    # 2. 读取并直接按 node_id 分组装入 dict
    if os.path.exists(log_path):
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entry = json.loads(line)
                            # 如果没有 node_id，归入 system
                            nid = entry.get("node_id") or "system"
                            if nid not in grouped_logs:
                                grouped_logs[nid] = []
                            grouped_logs[nid].append(entry)
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            print(f"读取日志失败: {e}")

    # 3. 直接返回纯净的结构化数据
    return {"task_id": task_id, "grouped_logs": grouped_logs}


@router.get("/{task_id}/log/structured")
def get_task_log_structured_api(
    task_id: str,
    node_id: str = Query(None, description="节点ID过滤"),
    after_line: int = Query(0, description="返回此行数之后的日志，用于增量拉取"),
):
    """
    获取结构化的任务日志，支持按节点过滤和增量拉取

    Args:
        task_id: 任务ID
        node_id: 可选，节点ID过滤
        after_line: 可选，返回此行数之后的日志（用于增量拉取）

    Returns:
        包含结构化日志数据和分组信息
    """
    result = get_task_log_structured(task_id, node_id, after_line)
    return result


@router.get("/{task_id}/log/jsonl")
def get_task_log_jsonl_api(task_id: str):
    logs = get_task_log_jsonl(task_id)
    if logs is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return logs


@router.get("/{task_id}/state")
def get_task_state_api(task_id: str):
    result = get_task_state(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return result


@router.post("/{task_id}/kill")
def kill_task_api(task_id: str):
    success = kill_task(task_id)
    if not success:
        raise HTTPException(status_code=404, detail="Task not found or already killed")
    return {"status": "ok", "message": f"Task {task_id} successfully killed."}


@router.post("/{task_id}/submit")
def submit_instruction_api(task_id: str, req: SubmitInstructionRequest):
    result, error = submit_instruction(task_id, req.node_id, req.content)
    if error:
        if "not found" in error.lower():
            raise HTTPException(status_code=404, detail=error)
        raise HTTPException(status_code=400, detail=error)
    return result


@router.delete("/{task_id}")
def delete_task_api(task_id: str):
    success = delete_task(task_id)
    if success:
        return {"status": "ok", "message": f"Task {task_id} successfully deleted."}
    raise HTTPException(status_code=404, detail="Task not found")


class TaskPushReq(BaseModel):
    message: str
    node_id: str = None


@router.post("/{task_id}/push")
def push_to_task(task_id: str, req: TaskPushReq):
    final_message = (
        f"@[{req.node_id}] 用户精确制导指令: {req.message}"
        if req.node_id
        else req.message
    )

    success = force_push_task(task_id, final_message)
    if success:
        return {"status": "ok", "message": "指令已注入"}
    raise HTTPException(status_code=404, detail="Task not active or injection failed")
