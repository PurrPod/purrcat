import os
import json
import datetime
from src.models import task as task_module
from src.utils.config import DATA_DIR

# ---------------------------------------------------------
# 全局 Agent 实例单例引用
# ---------------------------------------------------------
_global_agent = None


def set_global_agent(agent_instance):
    """供 main.py 初始化时注册全局 Agent 实例"""
    global _global_agent
    _global_agent = agent_instance


def get_global_agent():
    """获取 main.py 初始化的 agent 实例"""
    return _global_agent


# ---------------------------------------------------------
# Agent 相关接口
# ---------------------------------------------------------
def get_agent_history():
    """获取 agent 实例的当前历史记录 (对应 backend 中的 thought-chain)"""
    agent = get_global_agent()
    if agent:
        # 注意：Agent 类中实际存储历史的属性名是 current_history
        return agent.current_history
    return []


def force_push_agent(content: str):
    """消息注入，直接注入 agent 实例历史"""
    agent = get_global_agent()
    if agent:
        agent.force_push(content)
        return True
    return False


def get_window_token():
    """获取 agent 实例当前窗口的 token 用量"""
    agent = get_global_agent()
    if agent:
        return agent.window_token
    return 0


# ---------------------------------------------------------
# Task 相关接口
# ---------------------------------------------------------
def get_task_history(task_id: str):
    """输入 task_id，获取对应任务的历史"""
    # 1. 优先从内存中的活跃任务获取
    task_instance = task_module.TASK_INSTANCES.get(task_id)
    if task_instance:
        return task_instance.history

    # 2. 如果内存中没有，尝试从磁盘的 checkpoint 中恢复历史
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
    """将消息追加到 task 里（动态注入新指令）"""
    # 优先使用 task_module 中自带的指令注入函数
    success = task_module.inject_task_instruction(task_id, content)

    # 如果内存中找不到，且需要从磁盘复活死掉的任务，可参考 backend.py 的 /inject 接口逻辑在这里扩展
    return success


def get_task_list():
    """获取当前任务列表 (综合内存中的活跃任务与磁盘上的已完成任务)"""
    tasks = []

    # 1. 扫描内存中的活跃任务
    for task_id, task in task_module.TASK_INSTANCES.items():
        tasks.append({
            "id": task.task_id,
            "name": task.task_name,
            "state": task.state,
            "step": task.step,
            "expert_type": task.__class__.__name__,
            "create_time": task.create_time,
            "token_usage": task.token_usage,
            "checkpoint_dir": task.checkpoint_dir
        })

    # 2. 扫描磁盘上的历史任务 (参考 backend.py 的读取逻辑)
    base_dir = os.path.join(DATA_DIR, "checkpoints", "task")
    if os.path.isdir(base_dir):
        for entry in os.listdir(base_dir):
            checkpoint_path = os.path.join(base_dir, entry, "checkpoint.json")
            if not os.path.exists(checkpoint_path):
                continue

            try:
                with open(checkpoint_path, "r", encoding="utf-8") as f:
                    state = json.load(f)
            except Exception:
                continue

            saved_task_id = state.get("task_id")
            # 如果该任务已经在内存里，跳过，避免重复
            if saved_task_id and saved_task_id in task_module.TASK_INSTANCES:
                continue

            tasks.append({
                "id": saved_task_id,
                "name": state.get("name", entry),
                "state": state.get("state", "completed"),
                "step": state.get("step", 0),
                "expert_type": state.get("expert_type"),
                "create_time": state.get("create_time", ""),
                "token_usage": state.get("token_usage", 0),
                "checkpoint_dir": state.get("checkpoint_dir", os.path.join(base_dir, entry))
            })

    return tasks


def get_agent_max_token():
    """获取 agent 触发记忆压缩的 token 阈值 (agent.py 源码硬编码)"""
    return 100000


def get_task_max_token():
    """获取 task 触发记忆压缩的 token 阈值 (task.py 源码默认参数)"""
    return 120000


def get_task_window_token(task_id: str):
    """获取指定任务的 window_token"""
    import os, json
    from src.models.task import TASK_INSTANCES
    from src.utils.config import DATA_DIR

    task_instance = TASK_INSTANCES.get(task_id)
    if task_instance and hasattr(task_instance, 'window_token'):
        return task_instance.window_token

    # 若在内存中找不到活跃任务，尝试从磁盘状态中提取
    base_dir = os.path.join(DATA_DIR, "checkpoints", "task")
    if os.path.isdir(base_dir):
        # 注意任务的持久化目录名规则是 {task_name}_{create_time}，这里可能需要遍历匹配 task_id
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