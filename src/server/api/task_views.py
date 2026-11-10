"""任务 API 的视图组装：日志分组、checkpoint 定位与前端记忆合并。

路由层只做参数转发；本模块不启动引擎，只读内存与磁盘数据。
"""

from __future__ import annotations

import copy
import json
import os


def group_logs_by_node(logs) -> dict:
    """按 node_id 分组日志；缺省归入 system。"""
    grouped_logs = {}
    for entry in logs:
        nid = entry.get("node_id") or "system"
        grouped_logs.setdefault(nid, []).append(entry)
    return grouped_logs


def locate_checkpoint_dir(task_id: str, instances: dict, base_dir: str):
    """定位任务 checkpoint 目录：内存优先，磁盘按后缀模糊匹配兜底。"""
    task = instances.get(task_id)
    if task:
        return task.checkpoint_dir
    if os.path.exists(base_dir):
        for entry in os.listdir(base_dir):
            if task_id in entry:
                return os.path.join(base_dir, entry)
    return None


def _read_node_messages(node_path: str) -> list:
    """按优先级读取节点消息：memory.jsonl → live_memory.json → outputs.json。"""
    mem_file_jsonl = os.path.join(node_path, "memory.jsonl")
    live_file_json = os.path.join(node_path, "live_memory.json")
    out_file = os.path.join(node_path, "outputs.json")

    if os.path.exists(mem_file_jsonl):
        messages = []
        try:
            with open(mem_file_jsonl, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        messages.append(json.loads(line))
        except Exception:
            pass
        return messages
    if os.path.exists(live_file_json):
        try:
            with open(live_file_json, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    if os.path.exists(out_file):
        try:
            with open(out_file, "r", encoding="utf-8") as f:
                return json.load(f).get("messages", [])
        except Exception:
            return []
    return []


def collect_frontend_memory(task_id: str, instances: dict, checkpoint_dir) -> dict:
    """合并内存强制指令与落盘聊天记录，生成前端气泡需要的 node_memory。"""
    frontend_memory = {}
    if task_id in instances:
        frontend_memory = copy.deepcopy(instances[task_id].node_memory)

    if checkpoint_dir:
        nodes_dir = os.path.join(checkpoint_dir, "nodes")
        if os.path.exists(nodes_dir):
            for node_id in os.listdir(nodes_dir):
                node_path = os.path.join(nodes_dir, node_id)
                if not os.path.isdir(node_path):
                    continue
                messages = _read_node_messages(node_path)
                if messages:
                    if node_id not in frontend_memory:
                        frontend_memory[node_id] = {}
                    frontend_memory[node_id]["messages"] = messages
    return frontend_memory
