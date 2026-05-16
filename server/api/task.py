import json
import os
import traceback
import asyncio

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src.harness.process import TASK_INSTANCES

from src.utils.log_api import get_task_log_structured
from src.utils.task_api import (
    delete_task,
    force_push_task,
    get_task_list,
    get_task_log_jsonl,
    get_task_state,
    kill_task,
    submit_instruction,
)

router = APIRouter(prefix="/api/tasks", tags=["Tasks"])


class SubmitInstructionRequest(BaseModel):
    node_id: str
    content: str


@router.get("")
def list_tasks():
    print(f"[DEBUG] /api/tasks - 开始获取任务列表")
    try:
        result = get_task_list()
        print(f"[DEBUG] /api/tasks - 获取到 {len(result)} 个任务")
        return result
    except Exception as e:
        print(f"[ERROR] /api/tasks - 异常: {e}")
        traceback.print_exc()
        raise


@router.get("/{task_id}/log")
def get_task_log(task_id: str):
    print(f"[DEBUG] /api/tasks/{task_id}/log - 开始获取任务日志")
    try:
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
            print(f"[DEBUG] /api/tasks/{task_id}/log - 未找到检查点目录")
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

        print(f"[DEBUG] /api/tasks/{task_id}/log - 返回分组日志，共 {len(grouped_logs)} 组")
        # 3. 直接返回纯净的结构化数据
        return {"task_id": task_id, "grouped_logs": grouped_logs}
    except Exception as e:
        print(f"[ERROR] /api/tasks/{task_id}/log - 异常: {e}")
        traceback.print_exc()
        raise


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
    print(f"[DEBUG] /api/tasks/{task_id}/log/structured - 开始，node_id: {node_id}")
    try:
        result = get_task_log_structured(task_id, node_id, after_line)
        print(f"[DEBUG] /api/tasks/{task_id}/log/structured - 完成")
        return result
    except Exception as e:
        print(f"[ERROR] /api/tasks/{task_id}/log/structured - 异常: {e}")
        traceback.print_exc()
        raise


@router.get("/{task_id}/log/jsonl")
def get_task_log_jsonl_api(task_id: str):
    print(f"[DEBUG] /api/tasks/{task_id}/log/jsonl - 开始")
    try:
        logs = get_task_log_jsonl(task_id)
        if logs is None:
            print(f"[DEBUG] /api/tasks/{task_id}/log/jsonl - 任务未找到")
            raise HTTPException(status_code=404, detail="Task not found")
        print(f"[DEBUG] /api/tasks/{task_id}/log/jsonl - 完成，返回 {len(logs)} 条日志")
        return logs
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] /api/tasks/{task_id}/log/jsonl - 异常: {e}")
        traceback.print_exc()
        raise


@router.get("/{task_id}/state")
def get_task_state_api(task_id: str):
    print(f"[DEBUG] /api/tasks/{task_id}/state - 开始获取任务状态")
    try:
        result = get_task_state(task_id)
        if result is None:
            print(f"[DEBUG] /api/tasks/{task_id}/state - 任务未找到")
            raise HTTPException(status_code=404, detail="Task not found")
        print(f"[DEBUG] /api/tasks/{task_id}/state - 完成，状态: {result.get('state')}")
        return result
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] /api/tasks/{task_id}/state - 异常: {e}")
        traceback.print_exc()
        raise


@router.post("/{task_id}/kill")
def kill_task_api(task_id: str):
    print(f"[DEBUG] /api/tasks/{task_id}/kill - 开始终止任务")
    try:
        success = kill_task(task_id)
        if not success:
            print(f"[DEBUG] /api/tasks/{task_id}/kill - 任务未找到或已终止")
            raise HTTPException(status_code=404, detail="Task not found or already killed")
        print(f"[DEBUG] /api/tasks/{task_id}/kill - 任务已成功终止")
        return {"status": "ok", "message": f"Task {task_id} successfully killed."}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] /api/tasks/{task_id}/kill - 异常: {e}")
        traceback.print_exc()
        raise


@router.post("/{task_id}/submit")
async def submit_instruction_api(task_id: str, req: SubmitInstructionRequest):
    print(f"[DEBUG] /api/tasks/{task_id}/submit - 开始提交指令，node_id: {req.node_id}")
    try:
        result, error = submit_instruction(task_id, req.node_id, req.content)
        if error:
            print(f"[DEBUG] /api/tasks/{task_id}/submit - 错误: {error}")
            if "not found" in error.lower():
                raise HTTPException(status_code=404, detail=error)
            raise HTTPException(status_code=400, detail=error)
        print(f"[DEBUG] /api/tasks/{task_id}/submit - 指令已成功提交")
        
        # 如果任务之前已经休眠（处于 READY 状态），重新创建协程拉起引擎
        task = TASK_INSTANCES.get(task_id)
        if task:
            # 获取安全的字符串状态 (兼容 Enum)
            current_state = getattr(task.state, "value", task.state)
            if current_state == "ready":
                print(f"[DEBUG] 任务 {task_id} 已重置为 Ready，正在重新拉起引擎...")
                asyncio.create_task(task.run())

        return result
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] /api/tasks/{task_id}/submit - 异常: {e}")
        traceback.print_exc()
        raise


@router.delete("/{task_id}")
def delete_task_api(task_id: str):
    print(f"[DEBUG] /api/tasks/{task_id} - 开始删除任务")
    try:
        success = delete_task(task_id)
        if success:
            print(f"[DEBUG] /api/tasks/{task_id} - 任务已成功删除")
            return {"status": "ok", "message": f"Task {task_id} successfully deleted."}
        print(f"[DEBUG] /api/tasks/{task_id} - 任务未找到")
        raise HTTPException(status_code=404, detail="Task not found")
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] /api/tasks/{task_id} - 异常: {e}")
        traceback.print_exc()
        raise


class TaskPushReq(BaseModel):
    message: str
    node_id: str = None


@router.post("/{task_id}/push")
async def push_to_task(task_id: str, req: TaskPushReq):
    print(f"[DEBUG] /api/tasks/{task_id}/push - 开始推送指令")
    try:
        final_message = (
            f"@[{req.node_id}] 用户精确制导指令: {req.message}"
            if req.node_id
            else req.message
        )

        success = force_push_task(task_id, final_message)
        if success:
            print(f"[DEBUG] /api/tasks/{task_id}/push - 指令已成功注入")
            
            # 如果引擎是挂起/完结状态，重新拉起
            task = TASK_INSTANCES.get(task_id)
            if task and getattr(task.state, "value", task.state) == "ready":
                print(f"[DEBUG] 全局指令注入成功，正在重新拉起引擎...")
                asyncio.create_task(task.run())
                
            return {"status": "ok", "message": "指令已注入"}
            
        print(f"[DEBUG] /api/tasks/{task_id}/push - 任务未激活或注入失败")
        raise HTTPException(status_code=404, detail="Task not active or injection failed")
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] /api/tasks/{task_id}/push - 异常: {e}")
        traceback.print_exc()
        raise
