import json
import os
import shutil
from datetime import datetime

from src.harness.process import TASK_INSTANCES
from src.harness.process import kill_task as process_kill_task
from src.utils.config import DATA_DIR


def get_task_list():
    """🌟 修复：合并磁盘历史任务与内存活跃任务"""
    tasks_dict = {}

    # 1. 扫描磁盘上的所有持久化任务
    base_dir = os.path.join(DATA_DIR, "checkpoints", "task")
    if os.path.exists(base_dir):
        for entry in os.listdir(base_dir):
            chk_path = os.path.join(base_dir, entry, "checkpoint.json")
            if os.path.exists(chk_path):
                try:
                    with open(chk_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        tid = data.get("task_id")
                        if tid:
                            # 如果 checkpoint 中没有 create_time，尝试用文件修改时间
                            create_time = data.get("create_time", "")
                            if not create_time:
                                try:
                                    mtime = os.path.getmtime(chk_path)
                                    create_time = datetime.fromtimestamp(mtime).strftime("%Y%m%d%H%M%S")
                                except:
                                    create_time = "20250101000000"
                            
                            tasks_dict[tid] = {
                                "id": tid,
                                "name": data.get("name", "Unknown"),
                                "graph_name": data.get("graph_name", "default"),
                                "state": data.get("state", "idle"),
                                "step": data.get("step", 0),
                                "expert_type": "Task",
                                "create_time": create_time,
                                "token_usage": data.get("token_usage", 0),
                                "checkpoint_dir": data.get("checkpoint_dir", ""),
                            }
                except Exception as e:
                    print(f"读取历史任务 {entry} 失败: {e}")
                    continue

    # 2. 用内存中的活跃状态进行覆盖，保证实时性
    for task_id, task in TASK_INSTANCES.items():
        tasks_dict[task_id] = {
            "id": task.task_id,
            "name": task.task_name,
            "graph_name": getattr(task, "graph_name", "default"),
            "state": getattr(task.state, "value", task.state),  # 防御 Enum 类型
            "step": getattr(task, "step", 0),
            "expert_type": task.__class__.__name__,
            "create_time": task.create_time,
            "token_usage": getattr(task, "token_usage", 0),
            "checkpoint_dir": getattr(task, "checkpoint_dir", ""),
        }

    # 3. 按创建时间降序排序返回
    result = list(tasks_dict.values())
    result.sort(key=lambda x: str(x.get("create_time") or ""), reverse=True)
    return result


def get_task_state(task_id: str):
    """🌟 修复：非活跃任务直接读盘，避免重入导致的内存爆炸"""
    # 1. 如果任务在运行，直接从内存拿（最快，状态最新）
    task = TASK_INSTANCES.get(task_id)
    if task:
        return {
            "task_id": task.task_id,
            "state": getattr(task.state, "value", task.state),
            "graph": task.graph,
            "node_states": {k: getattr(v, "value", v) for k, v in task.node_state.items()},
            "outputs": task.outputs,
        }

    # 2. 如果任务已休眠/完成，去磁盘找，绝不重新实例化
    base_dir = os.path.join(DATA_DIR, "checkpoints", "task")
    if os.path.exists(base_dir):
        for entry in os.listdir(base_dir):
            if task_id in entry:
                chk_path = os.path.join(base_dir, entry, "checkpoint.json")
                if os.path.exists(chk_path):
                    try:
                        with open(chk_path, "r", encoding="utf-8") as f:
                            state_data = json.load(f)
                            return {
                                "task_id": state_data.get("task_id"),
                                "state": state_data.get("state"),
                                "graph": state_data.get("graph"),
                                # 兼容前端：将 dag_state 映射回 node_states
                                "node_states": state_data.get("dag_state", {}),
                                "outputs": state_data.get("outputs", {}),
                            }
                    except Exception:
                        pass
    return None


def get_task_log_jsonl(task_id: str):
    """🌟 修复：直接解析路径读取，不盲目唤醒任务引擎"""
    checkpoint_dir = None
    task = TASK_INSTANCES.get(task_id)
    
    if task:
        checkpoint_dir = task.checkpoint_dir
    else:
        base_dir = os.path.join(DATA_DIR, "checkpoints", "task")
        if os.path.exists(base_dir):
            for entry in os.listdir(base_dir):
                if task_id in entry:
                    checkpoint_dir = os.path.join(base_dir, entry)
                    break

    if not checkpoint_dir:
        return None

    log_file = os.path.join(checkpoint_dir, "log.jsonl")
    if not os.path.exists(log_file):
        return []

    logs = []
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        logs.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except Exception:
        pass
        
    return logs


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
        # 从磁盘找 checkpoint_dir
        checkpoint_dir = None
        base_dir = os.path.join(DATA_DIR, "checkpoints", "task")
        if os.path.exists(base_dir):
            for entry in os.listdir(base_dir):
                if task_id in entry:
                    checkpoint_dir = os.path.join(base_dir, entry)
                    break
    
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
    # ... [保持原有的实现] ...
    from src.harness import process as task_module

    task_instance = task_module.TASK_INSTANCES.get(task_id)
    if task_instance:
        return task_instance.history

    base_dir = os.path.join(DATA_DIR, "checkpoints", "task")
    if os.path.isdir(base_dir):
        for entry in os.listdir(base_dir):
            if task_id in entry or entry == task_id:
                history_path = os.path.join(base_dir, entry, "history.json")
                if os.path.exists(history_path):
                    with open(history_path, "r", encoding="utf-8") as f:
                        return json.load(f)
    return []


def force_push_task(task_id: str, content: str):
    from src.harness import process as task_module
    return task_module.inject_task_instruction(task_id, content)


def get_task_window_token(task_id: str):
    # ... [保持原有的实现] ...
    task_instance = TASK_INSTANCES.get(task_id)
    if task_instance and hasattr(task_instance, "window_token"):
        return task_instance.window_token

    base_dir = os.path.join(DATA_DIR, "checkpoints", "task")
    if os.path.isdir(base_dir):
        for task_dir in os.listdir(base_dir):
            checkpoint_path = os.path.join(base_dir, task_dir, "checkpoint.json")
            if os.path.exists(checkpoint_path):
                try:
                    with open(checkpoint_path, "r", encoding="utf-8") as f:
                        state = json.load(f)
                        if state.get("task_id") == task_id:
                            return state.get("window_token", 0)
                except Exception:
                    continue
    return 0


def get_task_max_token():
    return 120000
