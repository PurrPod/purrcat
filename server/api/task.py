import json
import os
import traceback
import asyncio

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

# 🌟 直接引入新版 Task 实例字典和状态枚举
from src.harness.process import TASK_INSTANCES
from src.harness.enums import NodeState, TaskState
from src.utils.config import DATA_DIR

router = APIRouter(prefix="/api/tasks", tags=["Tasks"])

class SubmitInstructionRequest(BaseModel):
    node_id: str
    content: str

class TaskPushReq(BaseModel):
    message: str
    node_id: str = None

@router.get("")
def list_tasks():
    """获取任务列表：直接从内存和磁盘快照读取"""
    try:
        tasks = []
        for task_id, task in TASK_INSTANCES.items():
            tasks.append({
                "id": task.task_id,
                "name": task.task_name,
                "state": task.state.value if hasattr(task.state, "value") else task.state,
                "create_time": getattr(task, "create_time", "")
            })
        # 按时间倒序
        tasks.sort(key=lambda x: x["create_time"], reverse=True)
        return tasks
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{task_id}/state")
def get_task_state_api(task_id: str):
    """🌟 新架构：获取极简的统一状态"""
    task = TASK_INSTANCES.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return {
        "task_id": task.task_id,
        "state": task.state.value if hasattr(task.state, "value") else task.state,
        "node_state": {k: v.value if hasattr(v, "value") else v for k, v in task.node_state.items()},
        "graph": task.graph
    }

@router.post("/{task_id}/submit")
async def submit_instruction_api(task_id: str, req: SubmitInstructionRequest):
    """🌟 新架构：使用规范化的指令注入 API"""
    task = TASK_INSTANCES.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # 使用新的规范化 API，自带类型校验和级联重置
    result = task.inject_instruction(req.node_id, req.content)
    
    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["message"])
    
    # 重新拉起大循环
    asyncio.create_task(task.run())

    return result

@router.post("/{task_id}/push")
async def push_to_task(task_id: str, req: TaskPushReq):
    """全局广播/后门注入：只向 Agent 节点注入"""
    task = TASK_INSTANCES.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    from src.harness.node.agent_node import AgentNode
    
    if req.node_id:
        # 指定单个节点，使用规范化 API
        result = task.inject_instruction(req.node_id, req.message)
        if result["status"] == "error":
            raise HTTPException(status_code=400, detail=result["message"])
    else:
        # 广播模式：只向所有 Agent 节点注入
        injected_count = 0
        for nid, node_instance in task.node_list.items():
            if isinstance(node_instance, AgentNode):
                task.inject_instruction(nid, req.message)
                injected_count += 1
        
        if injected_count == 0:
            return {"status": "success", "message": "未找到可注入的 Agent 节点"}

    asyncio.create_task(task.run())
    return {"status": "success", "message": "指令已广播注入"}

@router.get("/{task_id}/log")
def get_task_log(task_id: str):
    """统一日志读取，依赖全局 log.jsonl"""
    task = TASK_INSTANCES.get(task_id)
    if not task:
        return {"task_id": task_id, "grouped_logs": {}}

    log_path = os.path.join(task.checkpoint_dir, "log.jsonl")
    grouped_logs = {}

    if os.path.exists(log_path):
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entry = json.loads(line)
                        nid = entry.get("node_id") or "system"
                        grouped_logs.setdefault(nid, []).append(entry)
                    except json.JSONDecodeError:
                        continue

    return {"task_id": task_id, "grouped_logs": grouped_logs}

@router.delete("/{task_id}")
def delete_task_api(task_id: str):
    task = TASK_INSTANCES.pop(task_id, None)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task._killed = True # 触发销毁
    # 清理物理文件夹
    import shutil
    if os.path.exists(task.checkpoint_dir):
        shutil.rmtree(task.checkpoint_dir, ignore_errors=True)
        
    return {"status": "ok", "message": "Task destroyed."}
