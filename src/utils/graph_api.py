"""
Graph API - 为 FastAPI 后端提供 DAG 图谱管理接口
Graph 以文件夹为单位：{GRAPHS_DIR}/{name}/graph.json + asset/
"""

import glob
import json
import os
from typing import Any, Dict, List, Optional

from src.utils.config import SRC_DIR, GRAPHS_DIR

NODES_DIR = os.path.join(SRC_DIR, "harness", "node", "extensions")

# 已移除/改名的节点类型：迁移时用于检测旧 graph 引用并留下警告
# 注：file_writer 已重新恢复为「文件落盘」节点；preview 已改名为 file_reader
DEPRECATED_NODE_TYPES = {
    "image_generator",
    "preview",
    "text_file_reader",
    "if_else_router",
    "switch_router",
    "python_runner",
}


def _ensure_graphs_dir():
    os.makedirs(GRAPHS_DIR, exist_ok=True)


def graph_dir(name: str) -> str:
    return os.path.join(GRAPHS_DIR, name)


def graph_file(name: str) -> str:
    return os.path.join(GRAPHS_DIR, name, "graph.json")


def list_graphs() -> List[Dict[str, str]]:
    _ensure_graphs_dir()
    graphs = []
    for entry in os.listdir(GRAPHS_DIR):
        if os.path.isdir(os.path.join(GRAPHS_DIR, entry)):
            if os.path.exists(graph_file(entry)):
                graphs.append({"name": entry, "path": graph_file(entry)})
    return graphs


def get_all_nodes() -> List[Dict[str, Any]]:
    """获取所有可用的节点类型定义（从 node/extensions 目录读取）"""
    all_nodes = []
    if not os.path.exists(NODES_DIR):
        return all_nodes

    for node_json in glob.glob(os.path.join(NODES_DIR, "*", "*.json")):
        try:
            with open(node_json, "r", encoding="utf-8") as f:
                node_data = json.load(f)
            if node_data.get("type"):
                all_nodes.append(node_data)
        except Exception:
            pass
    return all_nodes


def get_graph(name: str) -> Optional[Dict[str, Any]]:
    _ensure_graphs_dir()
    folder_file = graph_file(name)
    if os.path.exists(folder_file):
        try:
            with open(folder_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def save_graph(name: str, graph_data: Dict[str, Any]) -> Dict[str, Any]:
    _ensure_graphs_dir()
    target = graph_dir(name)
    os.makedirs(target, exist_ok=True)
    os.makedirs(os.path.join(target, "asset"), exist_ok=True)
    with open(graph_file(name), "w", encoding="utf-8") as f:
        json.dump(graph_data, f, ensure_ascii=False, indent=2)
    return {"status": "ok", "name": name}


def migrate_graphs_to_folders() -> List[str]:
    """把旧单文件 graph 迁移为文件夹结构（幂等），返回迁移成功的名字列表。
    - {name}.json → {name}/graph.json，原文件改 .json.bak 保留
    - 旧格式 required_inputs 同步升级为 global_schema（运行时不再兼容旧格式）
    - 检测已移除节点类型的引用，写 {name}/DEPRECATED_NODES.txt 警告
    """
    _ensure_graphs_dir()
    migrated = []
    for entry in list(os.listdir(GRAPHS_DIR)):
        if not entry.endswith(".json"):
            continue
        name = entry[: -len(".json")]
        src_path = os.path.join(GRAPHS_DIR, entry)
        if not os.path.isfile(src_path):
            continue
        # 幂等：同名文件夹已存在则跳过
        if os.path.isdir(graph_dir(name)):
            continue
        try:
            with open(src_path, "r", encoding="utf-8") as f:
                graph_data = json.load(f)
        except Exception as e:
            print(f"⚠️ [Graph迁移] 跳过无法解析的 {entry}: {e}")
            continue

        # 旧格式 required_inputs → global_schema（一次性升级，运行时不兼容旧格式）
        if not graph_data.get("global_schema") and "required_inputs" in graph_data:
            graph_data["global_schema"] = {
                k: {"required": True, "description": v}
                for k, v in graph_data["required_inputs"].items()
            }
            del graph_data["required_inputs"]

        target_dir = graph_dir(name)
        os.makedirs(target_dir, exist_ok=True)
        os.makedirs(os.path.join(target_dir, "asset"), exist_ok=True)
        with open(graph_file(name), "w", encoding="utf-8") as f:
            json.dump(graph_data, f, ensure_ascii=False, indent=2)
        os.rename(src_path, src_path + ".bak")
        migrated.append(name)

        # 检测已移除节点引用
        removed = sorted(
            {
                n.get("type")
                for n in graph_data.get("nodes", [])
                if n.get("type") in DEPRECATED_NODE_TYPES
            }
        )
        if removed:
            note = os.path.join(target_dir, "DEPRECATED_NODES.txt")
            with open(note, "w", encoding="utf-8") as f:
                f.write(
                    f"此 graph 引用了已移除的节点类型: {', '.join(removed)}\n"
                    f"请用编辑器打开该 graph 替换这些节点后重新保存。\n"
                )
            print(
                f"⚠️ [Graph迁移] {name} 引用已移除节点: {removed}（已写入 DEPRECATED_NODES.txt）"
            )
    return migrated
