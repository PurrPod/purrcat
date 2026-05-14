import os
import json
import datetime
import re
from typing import Optional, Dict, List, Any


_task_log_cache = {}


def get_task_log_structured(task_id: str, node_id: str = None, after_line: int = 0) -> Dict[str, Any]:
    """
    获取结构化的任务日志，支持按节点过滤和增量拉取
    
    Args:
        task_id: 任务ID
        node_id: 可选，节点ID过滤
        after_line: 可选，返回此行数之后的日志（用于增量拉取）
    
    Returns:
        {
            "task_id": str,
            "total_lines": int,
            "logs": List[dict],
            "grouped_logs": Dict[str, List[dict]]  # 按节点分组
        }
    """
    from src.harness.process import TASK_INSTANCES
    from src.utils.config import DATA_DIR

    checkpoint_dir = None
    
    # 优先从运行中的任务实例获取
    task_instance = TASK_INSTANCES.get(task_id)
    if task_instance and hasattr(task_instance, 'checkpoint_dir'):
        checkpoint_dir = task_instance.checkpoint_dir
    else:
        # 尝试从 checkpoint 目录查找
        base_dir = os.path.join(DATA_DIR, "checkpoints", "task")
        if os.path.isdir(base_dir):
            for entry in os.listdir(base_dir):
                if task_id in entry:
                    checkpoint_dir = os.path.join(base_dir, entry)
                    break

    if not checkpoint_dir:
        return {
            "task_id": task_id,
            "total_lines": 0,
            "logs": [],
            "grouped_logs": {}
        }

    log_path = os.path.join(checkpoint_dir, "log.jsonl")
    if not os.path.exists(log_path):
        return {
            "task_id": task_id,
            "total_lines": 0,
            "logs": [],
            "grouped_logs": {}
        }

    logs = []
    grouped_logs = {}
    
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        total_lines = len(lines)
        start_idx = max(0, after_line)
        
        for i, line in enumerate(lines[start_idx:], start=start_idx):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                entry["_line"] = i  # 添加行号标记，用于增量拉取
                
                # 添加格式化的时间戳
                timestamp = entry.get("timestamp", 0)
                if timestamp:
                    entry["_time"] = datetime.datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")
                else:
                    entry["_time"] = "??:??:??"
                
                logs.append(entry)
                
                # 按节点分组
                node_key = entry.get("node_id", "system")
                if node_key not in grouped_logs:
                    grouped_logs[node_key] = []
                grouped_logs[node_key].append(entry)
                
            except json.JSONDecodeError:
                continue

    except Exception as e:
        return {
            "task_id": task_id,
            "total_lines": 0,
            "logs": [],
            "grouped_logs": {},
            "error": str(e)
        }

    # 如果指定了节点过滤
    if node_id:
        filtered_logs = grouped_logs.get(node_id, [])
        return {
            "task_id": task_id,
            "total_lines": len(filtered_logs),
            "logs": filtered_logs,
            "grouped_logs": {node_id: filtered_logs}
        }

    return {
        "task_id": task_id,
        "total_lines": total_lines,
        "logs": logs,
        "grouped_logs": grouped_logs
    }


def clean_log_entry(entry: dict) -> str:
    card_type = entry.get("card_type", "unknown")
    content = str(entry.get("content", ""))
    metadata = entry.get("metadata", {})

    if card_type == "tool_call":
        args = metadata.get("arguments", {})
        if "command" in args:
            cmd = args["command"]
            m = re.search(r"cat\s+>\s+([^\s]+)\s+<<\s*'PYEOF'", cmd)
            if m:
                file_name = m.group(1).split('/')[-1]
                return f"execute_command ➔ 写入文件: {file_name} (长代码已折叠)"

            clean_cmd = cmd.replace('\n', ' ')
            if len(clean_cmd) > 80:
                return f"execute_command ➔ {clean_cmd[:80]}..."
            return f"execute_command ➔ {clean_cmd}"

        elif args:
            args_str = ", ".join(f"{k}={v!r}" for k, v in args.items())
            tool_name = content.split("(")[0].replace("🔧 助手调起工具: ", "").strip()
            return f"{tool_name}({args_str})"

    elif card_type == "tool":
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
            pass

    prefixes_to_strip = ["🔧 助手调起工具: ", "📦 工具回传结果: ", "🤖 助手思考: ", "📋 "]
    for prefix in prefixes_to_strip:
        content = content.replace(prefix, "")

    return content.strip()


def format_task_log(task_id: str, checkpoint_dir: Optional[str] = None) -> str:
    from src.harness.process import TASK_INSTANCES
    from src.utils.config import DATA_DIR

    if checkpoint_dir is None:
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

    try:
        stat = os.stat(log_path)
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

        from rich.markup import escape
        cleaned_content = clean_log_entry(entry)
        content = escape(cleaned_content)

        if timestamp:
            time_str = datetime.datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")
        else:
            time_str = "??:??:??"

        color_map = {
            "system": "#9399b2",
            "thought": "#88c0d0",
            "tool_call": "#ebcb8b",
            "tool": "#a3be8c",
            "warning": "#d08770",
            "error": "#bf616a",
            "plan": "#81a1c1"
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

        label = card_type.upper().ljust(9)

        output_parts.append(f"[dim][{time_str}][/dim] [{color}]{emoji} {label}[/{color}] │ {content}")

    result = "\n".join(output_parts)

    try:
        stat = os.stat(log_path)
        _task_log_cache[task_id] = (stat.st_mtime_ns, stat.st_size, result)
    except OSError:
        pass

    return result
