import os
import json
import datetime
import copy
from src.harness import task as task_module
from src.utils.config import DATA_DIR
from src.agent.manager import get_agent
import os as _os

# ── format_task_log cache ──
_task_log_cache = {}  # task_id -> (mtime, size, formatted_text)

# ---------------------------------------------------------
# Agent 相关接口
# ---------------------------------------------------------
def get_agent_history():
    agent = get_agent()
    if agent:
        # 🟢 修复：必须深拷贝，防止后台正在思考写入时 UI 遍历导致崩溃
        return copy.deepcopy(agent.current_history)
    return []

def force_push_agent(text: str):
    # 直接推入 agent 的消息队列
    agent = get_agent()
    if agent:
        agent.force_push(text, type="user")
        return True
    return False


def flush_agent_memory():
    """强制触发主 Agent 记忆压缩与归档"""
    agent = get_agent()
    if agent:
        agent._check_and_summarize_memory(check_mode=False)
        return True
    return False


def get_window_token():
    """获取 agent 实例当前窗口的 token 用量"""
    agent = get_agent()
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
    return 1000000


def get_task_max_token():
    """获取 task 触发记忆压缩的 token 阈值 (task.py 源码默认参数)"""
    return 120000


def get_task_window_token(task_id: str):
    """获取指定任务的 window_token"""
    import os, json
    from src.harness.task import TASK_INSTANCES
    from src.utils.config import DATA_DIR

    task_instance = TASK_INSTANCES.get(task_id)
    if task_instance and hasattr(task_instance, 'window_token'):
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


def format_task_log(task_id: str) -> str:
    """解析并格式化任务的日志输出，按card_type分组展示"""
    from src.harness.task import TASK_INSTANCES

    task_instance = TASK_INSTANCES.get(task_id)
    if task_instance and hasattr(task_instance, 'checkpoint_dir'):
        checkpoint_dir = task_instance.checkpoint_dir
    else:
        base_dir = os.path.join(DATA_DIR, "checkpoints", "task")
        checkpoint_dir = None
        if os.path.isdir(base_dir):
            for entry in os.listdir(base_dir):
                if task_id in entry:
                    checkpoint_dir = os.path.join(base_dir, entry)
                    break

    if not checkpoint_dir:
        return f"任务 {task_id} 未找到"

    log_path = os.path.join(checkpoint_dir, "log.jsonl")
    if not os.path.exists(log_path):
        return f"暂无日志内容 (任务 {task_id})"

    try:
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return f"读取日志失败 (任务 {task_id})"

    if not lines:
        return f"暂无日志内容 (任务 {task_id})"

    CARD_PREFIXES = {
        "system": "🔔",
        "thought": "💭",
        "tool_call": "🔧",
        "tool": "📦",
        "warning": "⚠️",
        "error": "❌",
        "plan": "📋",
    }

    sections = {}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        card_type = entry.get("card_type", "unknown")
        timestamp = entry.get("timestamp", 0)
        content = entry.get("content", "")

        if timestamp:
            time_str = datetime.datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")
        else:
            time_str = "??:??:??"

        prefix = CARD_PREFIXES.get(card_type, "📄")
        key = (card_type, prefix)
        if key not in sections:
            sections[key] = []
        sections[key].append(f"[{time_str}] {content}")

    if not sections:
        return f"Task {task_id}: no log content."

    output_parts = []
    output_parts.append(f"── Task Log ({len(lines)} entries) ──")

    order_priority = ["system", "thought", "tool_call", "tool", "warning", "error", "plan"]
    compact_labels = {"system": "SYS", "thought": "THT", "tool_call": "TCL", "tool": "TOL", "warning": "WRN", "error": "ERR", "plan": "PLN"}

    for (card_type, prefix), entries in sorted(sections.items(), key=lambda x: order_priority.index(x[0][0]) if x[0][0] in order_priority else 99):
        label = compact_labels.get(card_type, card_type.upper())
        for entry in entries:
            output_parts.append(f" [{label}] {entry}")

    return "\n".join(output_parts)