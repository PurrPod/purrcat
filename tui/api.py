import os
import json
import datetime
import copy
import re
from src.harness import task as task_module
from src.utils.config import DATA_DIR
from src.agent.manager import get_agent
import os as _os

def clean_log_entry(entry: dict) -> str:
    """对原始日志 JSON 进行降噪和极简提取"""
    card_type = entry.get("card_type", "unknown")
    content = str(entry.get("content", ""))
    metadata = entry.get("metadata", {})

    # 1. 极简处理工具调用 (Tool Call)
    if card_type == "tool_call":
        args = metadata.get("arguments", {})
        if "command" in args:
            cmd = args["command"]
            # 正则匹配长代码写入：提取 cat > 文件名 << 'PYEOF'
            m = re.search(r"cat\s+>\s+([^\s]+)\s+<<\s*'PYEOF'", cmd)
            if m:
                # 只保留文件名，比如取路径最后一部分
                file_name = m.group(1).split('/')[-1]
                return f"execute_command ➔ 写入文件: {file_name} (长代码已折叠)"
            
            # 其他一般长命令，超过 80 字符折叠
            clean_cmd = cmd.replace('\n', ' ')
            if len(clean_cmd) > 80:
                return f"execute_command ➔ {clean_cmd[:80]}..."
            return f"execute_command ➔ {clean_cmd}"
            
        elif args:
            # 对于 update_plan 等其他命令，显示参数摘要
            args_str = ", ".join(f"{k}={v!r}" for k, v in args.items())
            # 提取工具名称，比如 update_plan
            tool_name = content.split("(")[0].replace("🔧 助手调起工具: ", "").strip()
            return f"{tool_name}({args_str})"

    # 2. 极简处理工具返回结果 (Tool Result)
    elif card_type == "tool":
        # 尝试从包裹的字符串中解析出真正的 JSON
        try:
            json_start = content.find("{")
            if json_start != -1:
                res = json.loads(content[json_start:])
                if res.get("type") == "text":
                    inner_content = res.get("content", {})
                    exit_code = inner_content.get("exit_code")
                    output = inner_content.get("output", "").strip()
                    
                    if exit_code == 0:
                        out_msg = f", 输出: {output[:30]}..." if output else ", 无标准输出"
                        return f"✅ 执行成功 (exit_code: 0{out_msg})"
                    else:
                        return f"❌ 执行失败 (exit_code: {exit_code}, 报错: {output[:50]}...)"
        except Exception:
            pass # 解析失败则保留原样

    # 3. 处理思考和计划 (Thought / Plan)
    # 删掉默认带的冗余前缀，让画面更干净
    prefixes_to_strip = ["🔧 助手调起工具: ", "📦 工具回传结果: ", "🤖 助手思考: ", "📋 "]
    for prefix in prefixes_to_strip:
        content = content.replace(prefix, "")

    return content.strip()

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
    """Parse and format task log output with file-change caching"""
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
        return f"Task {task_id} not found"

    log_path = os.path.join(checkpoint_dir, "log.jsonl")
    if not os.path.exists(log_path):
        return f"No log yet (Task {task_id})"

    # Cache check: only re-read if file changed
    try:
        stat = _os.stat(log_path)
        cached = _task_log_cache.get(task_id)
        if cached and cached[0] == stat.st_mtime_ns and cached[1] == stat.st_size:
            return cached[2]
    except OSError:
        pass

    try:
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return f"Read log failed (Task {task_id})"

    if not lines:
        return f"No log yet (Task {task_id})"

    # 🟢 修复：改为时间序列排序，并使用 Rich 语法结构化高亮与对齐
    output_parts = [f"[bold deep_sky_blue]── Task {task_id} 执行日志 ──[/bold deep_sky_blue]\n"]

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
        
        # 🟢 修复 3：使用 rich 原生 escape 转义真实的日志内容，防止语法冲突崩溃
        from rich.markup import escape
        # 先清洗日志内容，再进行转义
        cleaned_content = clean_log_entry(entry)
        content = escape(cleaned_content)

        if timestamp:
            time_str = datetime.datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")
        else:
            time_str = "??:??:??"

        # 为不同的卡片类型赋予终端色彩和 emoji
        color_map = {
            "system": "dim white",
            "thought": "bold cyan",
            "tool_call": "bold yellow",
            "tool": "bold green",
            "warning": "bold orange3",
            "error": "bold red",
            "plan": "bold dodger_blue1"
        }
        emoji_map = {
            "system": "⚙️",
            "thought": "🤖",
            "tool_call": "🔧",
            "tool": "📦",
            "warning": "⚠️",
            "error": "❌",
            "plan": "📋"
        }
        color = color_map.get(card_type, "white")
        emoji = emoji_map.get(card_type, "📄")
        
        # 强制标签占用 9 个字符宽度，保证日志文本完美左对齐
        label = card_type.upper().ljust(9)

        output_parts.append(f"[dim][{time_str}][/dim] [{color}]{emoji} {label}[/{color}] │ {content}")

    result = "\n".join(output_parts)

    # Write to cache
    try:
        stat = _os.stat(log_path)
        _task_log_cache[task_id] = (stat.st_mtime_ns, stat.st_size, result)
    except OSError:
        pass

    return result
