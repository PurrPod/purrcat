import asyncio
import traceback

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# 用于激活运行中任务注入指令
from src.harness.process import TASK_INSTANCES

# 引入统一封装的 API，支持访问休眠与活跃任务
from src.utils.task_api import (
    get_task_list,
    get_task_state,
    get_task_log_jsonl,
    delete_task,
)

router = APIRouter(prefix="/api/tasks", tags=["Tasks"])


class SubmitInstructionRequest(BaseModel):
    node_id: str
    content: str


class TaskPushReq(BaseModel):
    message: str
    node_id: str = None


@router.get("")
def list_tasks_api():
    """获取任务列表：正确使用重构后的 API，合并磁盘与内存"""
    try:
        return get_task_list()
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{task_id}/state")
def get_task_state_endpoint(task_id: str):
    """获取极简的统一状态 (支持活跃与休眠任务直接读取)"""
    state_data = get_task_state(task_id)
    if not state_data:
        raise HTTPException(status_code=404, detail="Task not found")
    return state_data


@router.post("/{task_id}/submit")
async def submit_instruction_api(task_id: str, req: SubmitInstructionRequest):
    """注入人工指令（任务必须在内存中处于活跃状态）"""
    task = TASK_INSTANCES.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found or not active")

    # 使用新的规范化 API，自带类型校验和级联重置
    result = task.inject_instruction(req.node_id, req.content)

    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["message"])

    # 重新拉起大循环
    asyncio.create_task(task.run())

    return result


@router.post("/{task_id}/push")
async def push_to_task(task_id: str, req: TaskPushReq):
    """全局广播/后门注入：只向 Agent 节点注入（任务必须在内存中处于活跃状态）"""
    task = TASK_INSTANCES.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found or not active")

    from src.harness.node.agent_node import AgentNode

    if req.node_id:
        # 指定单个节点，使用规范化 API
        result = task.inject_instruction(req.node_id, req.message)
        if result["status"] == "error":
            raise HTTPException(status_code=400, detail=result["message"])
    else:
        # 广播模式：向所有 Agent 节点注入
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
def get_task_log_endpoint(task_id: str):
    """统一日志读取（直接读纯文本盘，绝不瞎唤醒休眠引擎）"""
    logs = get_task_log_jsonl(task_id)
    if logs is None:
        return {"task_id": task_id, "grouped_logs": {}}

    grouped_logs = {}
    for entry in logs:
        nid = entry.get("node_id") or "system"
        grouped_logs.setdefault(nid, []).append(entry)

    return {"task_id": task_id, "grouped_logs": grouped_logs}


@router.delete("/{task_id}")
def delete_task_endpoint(task_id: str):
    """删除任务：使用安全的物理删除 API，同时支持清理休眠和活跃任务"""
    if delete_task(task_id):
        return {"status": "ok", "message": "Task destroyed."}
    raise HTTPException(status_code=404, detail="Task not found or delete failed")


@router.post("/{task_id}/nodes/{node_id}/reset")
async def reset_node_api(task_id: str, node_id: str):
    """供前端点击重置节点后调用，触发级联清理及引擎重启"""
    task = TASK_INSTANCES.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found or not active")

    result = task.reset_node(node_id)
    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["message"])

    # 状态成功重置为 READY 后，重新拉起大循环继续跑
    asyncio.create_task(task.run())

    return result
