import asyncio
import traceback

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

# 用于激活运行中任务注入指令
from src.harness.process import TASK_INSTANCES, Task, kill_task

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


class RunTaskRequest(BaseModel):
    task_name: str
    graph_name: str
    inputs: dict = {}


@router.get("")
def list_tasks_api():
    """获取任务列表：正确使用重构后的 API，合并磁盘与内存"""
    try:
        return get_task_list()
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run")
async def run_task_api(req: RunTaskRequest, background_tasks: BackgroundTasks):
    """创建并启动新任务：接收工作流名称和初始输入参数，抛入后台异步执行"""
    try:
        task = Task(
            task_name=req.task_name,
            graph_name=req.graph_name,
            inputs=req.inputs,
        )

        if task.state.value == "error" and task.init_error:
            raise HTTPException(status_code=400, detail=task.init_error)

        background_tasks.add_task(task.run)

        return {
            "status": "success",
            "task_id": task.task_id,
            "message": "Task started in background.",
        }
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{task_id}/state")
def get_task_state_endpoint(task_id: str):
    """获取极简的统一状态，并拼装出前端气泡需要的 memory (支持活跃与休眠任务)"""
    state_data = get_task_state(task_id)
    if not state_data:
        raise HTTPException(status_code=404, detail="Task not found")

    import os
    import json
    import copy
    from src.utils.config import DATA_DIR

    frontend_memory = {}

    # 1. 定位物理文件夹 (内存中有就用内存的路径，没有就扫硬盘)
    checkpoint_dir = None
    if task_id in TASK_INSTANCES:
        checkpoint_dir = TASK_INSTANCES[task_id].checkpoint_dir
        # 把内存里的强制指令也带上
        frontend_memory = copy.deepcopy(TASK_INSTANCES[task_id].node_memory)
    else:
        base_dir = os.path.join(DATA_DIR, "checkpoints", "task")
        if os.path.exists(base_dir):
            for entry in os.listdir(base_dir):
                if task_id in entry:
                    checkpoint_dir = os.path.join(base_dir, entry)
                    break

    # 2. 读取实时聊天记录 (解决运行时前端空白的问题)
    if checkpoint_dir:
        nodes_dir = os.path.join(checkpoint_dir, "nodes")
        if os.path.exists(nodes_dir):
            for node_id in os.listdir(nodes_dir):
                node_path = os.path.join(nodes_dir, node_id)
                if not os.path.isdir(node_path):
                    continue

                mem_file_jsonl = os.path.join(node_path, "memory.jsonl")
                live_file_json = os.path.join(node_path, "live_memory.json")
                out_file = os.path.join(node_path, "outputs.json")

                messages = []

                # 🎯 优先级 1: 读取 JSONL 格式的实时记录
                if os.path.exists(mem_file_jsonl):
                    try:
                        with open(mem_file_jsonl, "r", encoding="utf-8") as f:
                            for line in f:
                                line = line.strip()
                                if line:
                                    messages.append(json.loads(line))
                    except Exception:
                        pass
                # 🎯 优先级 2: 读取 JSON 格式的实时记录
                elif os.path.exists(live_file_json):
                    try:
                        with open(live_file_json, "r", encoding="utf-8") as f:
                            messages = json.load(f)
                    except Exception:
                        pass
                # 🎯 优先级 3: 节点已结束，读取最终产出兜底
                elif os.path.exists(out_file):
                    try:
                        with open(out_file, "r", encoding="utf-8") as f:
                            out_data = json.load(f)
                            messages = out_data.get("messages", [])
                    except Exception:
                        pass

                if messages:
                    if node_id not in frontend_memory:
                        frontend_memory[node_id] = {}
                    frontend_memory[node_id]["messages"] = messages

    state_data["node_memory"] = frontend_memory
    return state_data


@router.post("/{task_id}/submit")
async def submit_instruction_api(task_id: str, req: SubmitInstructionRequest):
    """注入人工指令（任务必须在内存中处于活跃状态）"""
    task = TASK_INSTANCES.get(task_id)

    # 如果任务不在内存中，尝试从磁盘加载
    if not task:
        from src.harness.process import Task
        import os
        from src.utils.config import DATA_DIR

        checkpoints_dir = os.path.join(DATA_DIR, "checkpoints", "task")
        task_dir = None

        # 查找匹配的任务目录
        for dir_name in os.listdir(checkpoints_dir):
            if dir_name.endswith(f"_{task_id}") or dir_name == task_id:
                task_dir = os.path.join(checkpoints_dir, dir_name)
                break

        if task_dir and os.path.exists(task_dir):
            task = Task.load_checkpoint(task_dir)
            if task:
                print(f"✅ 从磁盘加载任务到内存: {task.task_id}")
            else:
                raise HTTPException(
                    status_code=404, detail="Task not found or not active"
                )
        else:
            raise HTTPException(status_code=404, detail="Task not found or not active")

    # 使用新的规范化 API，自带类型校验和级联重置
    result = task.inject_instruction(req.node_id, req.content)

    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["message"])

    from src.harness.enums import TaskState

    if task.state != TaskState.RUNNING:
        asyncio.create_task(task.run())

    return result


@router.post("/{task_id}/push")
async def push_to_task(task_id: str, req: TaskPushReq):
    """精确注入：只向指定 Agent 节点注入（任务必须在内存中处于活跃状态）"""
    task = TASK_INSTANCES.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found or not active")

    if not req.node_id:
        raise HTTPException(
            status_code=400,
            detail="拒绝操作：必须指定 node_id，已废弃不安全的全局广播注入。",
        )

    result = task.inject_instruction(req.node_id, req.message)
    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["message"])

    from src.harness.enums import TaskState

    if task.state != TaskState.RUNNING:
        asyncio.create_task(task.run())

    return {"status": "success", "message": "指令已精确注入"}


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

    from src.harness.enums import TaskState

    if task.state != TaskState.RUNNING:
        asyncio.create_task(task.run())

    return result


@router.post("/{task_id}/stop")
def stop_task_api(task_id: str):
    """优雅终止运行中的任务：与 DELETE 不同，这里只杀死进程但保留 checkpoint 供后续查看"""
    if kill_task(task_id):
        return {"status": "success", "message": "Task killed gracefully."}
    raise HTTPException(status_code=404, detail="Task not active or not found.")
