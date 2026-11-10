"""
Graph API - 为 FastAPI 后端提供 DAG 图谱管理接口
Graph 以文件夹为单位：{GRAPHS_DIR}/{name}/graph.json + asset/
"""

import glob
import json
import os
from typing import Any, Dict, List, Optional

from src.utils._fs import write_json
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


def _root(root: Optional[str]) -> str:
    return root if root is not None else GRAPHS_DIR


def _ensure_graphs_dir(root: Optional[str] = None) -> None:
    os.makedirs(_root(root), exist_ok=True)


def graph_dir(name: str, root: Optional[str] = None) -> str:
    return os.path.join(_root(root), name)


def graph_file(name: str, root: Optional[str] = None) -> str:
    return os.path.join(_root(root), name, "graph.json")


def list_graphs(root: Optional[str] = None) -> List[Dict[str, str]]:
    _ensure_graphs_dir(root)
    graphs = []
    for entry in os.listdir(_root(root)):
        if os.path.isdir(graph_dir(entry, root)):
            if os.path.exists(graph_file(entry, root)):
                graphs.append({"name": entry, "path": graph_file(entry, root)})
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


def get_graph(name: str, root: Optional[str] = None) -> Optional[Dict[str, Any]]:
    _ensure_graphs_dir(root)
    folder_file = graph_file(name, root)
    if os.path.exists(folder_file):
        try:
            with open(folder_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def save_graph(
    name: str, graph_data: Dict[str, Any], root: Optional[str] = None
) -> Dict[str, Any]:
    _ensure_graphs_dir(root)
    target = graph_dir(name, root)
    os.makedirs(target, exist_ok=True)
    os.makedirs(os.path.join(target, "asset"), exist_ok=True)
    write_json(graph_file(name, root), graph_data)
    return {"status": "ok", "name": name}


def upgrade_required_inputs(graph_data: Dict[str, Any]) -> Dict[str, Any]:
    """旧格式 required_inputs → global_schema（一次性升级，运行时不兼容旧格式）。"""
    if graph_data.get("global_schema") or "required_inputs" not in graph_data:
        return graph_data
    upgraded = dict(graph_data)
    upgraded["global_schema"] = {
        k: {"required": True, "description": v}
        for k, v in graph_data["required_inputs"].items()
    }
    del upgraded["required_inputs"]
    return upgraded


def deprecated_node_types(graph_data: Dict[str, Any]) -> List[str]:
    return sorted(
        {
            n.get("type")
            for n in graph_data.get("nodes", [])
            if n.get("type") in DEPRECATED_NODE_TYPES
        }
    )


def deprecated_note(removed: List[str]) -> str:
    return (
        f"此 graph 引用了已移除的节点类型: {', '.join(removed)}\n"
        f"请用编辑器打开该 graph 替换这些节点后重新保存。\n"
    )


def migrate_graphs_to_folders(root: Optional[str] = None) -> List[str]:
    """把旧单文件 graph 迁移为文件夹结构（幂等），返回迁移成功的名字列表。
    - {name}.json → {name}/graph.json，原文件改 .json.bak 保留
    - 旧格式 required_inputs 同步升级为 global_schema（运行时不再兼容旧格式）
    - 检测已移除节点类型的引用，写 {name}/DEPRECATED_NODES.txt 警告
    """
    _ensure_graphs_dir(root)
    graphs_root = _root(root)
    migrated = []
    for entry in list(os.listdir(graphs_root)):
        if not entry.endswith(".json"):
            continue
        name = entry[: -len(".json")]
        src_path = os.path.join(graphs_root, entry)
        if not os.path.isfile(src_path):
            continue
        # 幂等：同名文件夹已存在则跳过
        if os.path.isdir(graph_dir(name, root)):
            continue
        try:
            with open(src_path, "r", encoding="utf-8") as f:
                graph_data = json.load(f)
        except Exception as e:
            print(f"⚠️ [Graph迁移] 跳过无法解析的 {entry}: {e}")
            continue

        graph_data = upgrade_required_inputs(graph_data)

        target_dir = graph_dir(name, root)
        os.makedirs(target_dir, exist_ok=True)
        os.makedirs(os.path.join(target_dir, "asset"), exist_ok=True)
        write_json(graph_file(name, root), graph_data)
        os.rename(src_path, src_path + ".bak")
        migrated.append(name)

        # 检测已移除节点引用
        removed = deprecated_node_types(graph_data)
        if removed:
            note = os.path.join(target_dir, "DEPRECATED_NODES.txt")
            with open(note, "w", encoding="utf-8") as f:
                f.write(deprecated_note(removed))
            print(
                f"⚠️ [Graph迁移] {name} 引用已移除节点: {removed}（已写入 DEPRECATED_NODES.txt）"
            )
    return migrated
