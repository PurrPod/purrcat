import asyncio
import os
import shutil

from src.harness.process import TASK_INSTANCES
from src.harness.process import kill_task as process_kill_task
from src.utils import task_store


def get_task_list():
    """🌟 修复：合并磁盘历史任务与内存活跃任务"""
    tasks_dict = task_store.scan_disk_tasks(task_store.checkpoints_root())

    # 用内存中的活跃状态进行覆盖，保证实时性
    for task_id, task in TASK_INSTANCES.items():
        tasks_dict[task_id] = task_store.build_active_task(task)

    return task_store.sort_task_summaries(list(tasks_dict.values()))


def get_task_state(task_id: str):
    """🌟 修复：非活跃任务直接读盘，避免重入导致的内存爆炸"""
    # 1. 如果任务在运行，直接从内存拿（最快，状态最新）
    task = TASK_INSTANCES.get(task_id)
    if task:
        return {
            "task_id": task.task_id,
            "state": getattr(task.state, "value", task.state),
            "graph": task.graph,
            "node_states": {
                k: getattr(v, "value", v) for k, v in task.node_state.items()
            },
            "outputs": task.outputs,
        }

    # 2. 如果任务已休眠/完成，去磁盘找，绝不重新实例化
    state_data = task_store.load_task_checkpoint(task_id)
    if state_data is not None:
        return {
            "task_id": state_data.get("task_id"),
            "state": state_data.get("state"),
            "graph": state_data.get("graph"),
            # 兼容前端：将 dag_state 映射回 node_states
            "node_states": state_data.get("dag_state", {}),
            "outputs": state_data.get("outputs", {}),
        }
    return None


def get_task_log_jsonl(task_id: str):
    """🌟 修复：直接解析路径读取，不盲目唤醒任务引擎"""
    task = TASK_INSTANCES.get(task_id)
    checkpoint_dir = task_store.resolve_checkpoint_dir(task_id, task)
    if not checkpoint_dir:
        return None
    return task_store.read_log_entries(os.path.join(checkpoint_dir, "log.jsonl"))


# ==========================================
# 下方为原有业务方法，保持不变
# ==========================================


def kill_task(task_id: str):
    return process_kill_task(task_id)


def submit_instruction(task_id: str, node_id: str, content: str):
    task = TASK_INSTANCES.get(task_id)
    if not task:
        return None, "Task not found or not active"

    if node_id not in task.node_list:
        return None, f"Node '{node_id}' not found in task '{task_id}'"

    task.submit_request(node_id, content)
    return {"status": "ok", "message": f"Instruction submitted to node {node_id}"}, None


def delete_task(task_id: str):
    """真正删除任务：终止、从内存移除、删除磁盘文件夹"""
    # 1. 先终止任务
    process_kill_task(task_id)

    # 2. 从内存中移除
    if task_id in TASK_INSTANCES:
        task = TASK_INSTANCES[task_id]
        checkpoint_dir = task.checkpoint_dir
        del TASK_INSTANCES[task_id]
    else:
        checkpoint_dir = task_store.resolve_checkpoint_dir(task_id)

    # 3. 删除磁盘文件夹
    if checkpoint_dir and os.path.exists(checkpoint_dir):
        try:
            shutil.rmtree(checkpoint_dir)
            print(f"[DEBUG] 已删除任务文件夹: {checkpoint_dir}")
        except Exception as e:
            print(f"[ERROR] 删除任务文件夹失败: {e}")
            return False

    return True


def get_task_history(task_id: str):
    from src.harness import process as task_module

    task_instance = task_module.TASK_INSTANCES.get(task_id)
    if task_instance:
        return task_instance.history
    return task_store.read_history(task_id)


def force_push_task(task_id: str, content: str):
    """供 TUI 使用的全局广播注入：向所有 Agent 节点注入指令并唤醒"""
    from src.harness.node.agent_node import AgentNode
    from src.harness.enums import TaskState

    task = TASK_INSTANCES.get(task_id)
    if not task:
        return False

    # 🌟 修复：注入前记录状态，任务仍在运行时交给现有引擎消费指令，绝不重复拉起第二个引擎
    was_running = task.state == TaskState.RUNNING

    injected = False
    for nid, node_instance in task.node_list.items():
        if isinstance(node_instance, AgentNode):
            task.inject_instruction(nid, content)
            injected = True

    if injected and not was_running:
        # 尝试拉起大循环（非阻塞）
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(task.run())
        except RuntimeError:
            pass
        return True
    return False


def get_task_window_token(task_id: str):
    task_instance = TASK_INSTANCES.get(task_id)
    if task_instance and hasattr(task_instance, "window_token"):
        return task_instance.window_token
    return task_store.read_window_token(task_id)


def get_task_max_token():
    return 120000
