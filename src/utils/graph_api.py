"""
Graph API - 为 FastAPI 后端提供 DAG 图谱管理接口
"""

import glob
import json
import os
from typing import Any, Dict, List, Optional

from src.utils.config import SRC_DIR

GRAPHS_DIR = os.path.join(SRC_DIR, "harness", "graph")
NODES_DIR = os.path.join(SRC_DIR, "harness", "node", "extensions")


def _ensure_graphs_dir():
    os.makedirs(GRAPHS_DIR, exist_ok=True)


def list_graphs() -> List[str]:
    _ensure_graphs_dir()
    graphs = []
    for filename in os.listdir(GRAPHS_DIR):
        if filename.endswith(".json"):
            graphs.append(filename)
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


def get_graph(filename: str) -> Optional[Dict[str, Any]]:
    _ensure_graphs_dir()
    if not filename.endswith(".json"):
        filename = f"{filename}.json"
    filepath = os.path.join(GRAPHS_DIR, filename)
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_graph(filename: str, graph_data: Dict[str, Any]) -> Dict[str, Any]:
    _ensure_graphs_dir()
    if not filename.endswith(".json"):
        filename = f"{filename}.json"
    filepath = os.path.join(GRAPHS_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(graph_data, f, ensure_ascii=False, indent=2)
    return {"status": "ok", "filename": filename}
