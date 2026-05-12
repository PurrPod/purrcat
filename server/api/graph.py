import os
import json
from fastapi import APIRouter, HTTPException
from typing import Dict, Any

from src.utils.config import BASE_DIR

router = APIRouter(prefix="/api/graphs", tags=["DAG Graphs"])

# 定义目录路径
GRAPH_DIR = os.path.join(BASE_DIR, "src", "harness", "graph")
NODE_DIR = os.path.join(BASE_DIR, "src", "harness", "node")

os.makedirs(GRAPH_DIR, exist_ok=True)

# 1. 获取已有的节点信息和条目 (从 harness/node/ 下获取所有的节点大 JSON)
@router.get("/nodes")
def get_all_nodes():
    nodes = []
    if os.path.exists(NODE_DIR):
        # 遍历 node 目录下的所有子文件夹
        for folder_name in os.listdir(NODE_DIR):
            folder_path = os.path.join(NODE_DIR, folder_name)
            if os.path.isdir(folder_path):
                # 兼容查找同名 .json 或者 meta.json 作为节点的描述文件
                json_path = os.path.join(folder_path, f"{folder_name}.json")
                if not os.path.exists(json_path):
                    json_path = os.path.join(folder_path, "meta.json")
                
                if os.path.exists(json_path):
                    try:
                        with open(json_path, "r", encoding="utf-8") as f:
                            node_data = json.load(f)
                            nodes.append(node_data)
                    except Exception as e:
                        print(f"Error loading node data from {json_path}: {e}")
    return nodes

# (辅助接口) 获取可用的 graph 列表
@router.get("")
def list_graphs():
    files = []
    if os.path.exists(GRAPH_DIR):
        for f in os.listdir(GRAPH_DIR):
            if f.endswith(".json"):
                files.append({"name": f, "path": os.path.join(GRAPH_DIR, f)})
    return files

# 2. 获取 graph/.json 文件内容
@router.get("/{filename}")
def get_graph(filename: str):
    filepath = os.path.join(GRAPH_DIR, filename)
    if not os.path.exists(filepath):
        filepath = os.path.join(GRAPH_DIR, f"{filename}.json")
        if not os.path.exists(filepath):
            raise HTTPException(status_code=404, detail="Graph not found")
    
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)

# 3. 接收 JSON 并在 harness/graph/ 下落盘
@router.post("/{filename}")
def save_graph(filename: str, graph_data: Dict[str, Any]):
    if not filename.endswith(".json"):
        filename += ".json"
    filepath = os.path.join(GRAPH_DIR, filename)
    
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(graph_data, f, ensure_ascii=False, indent=2)
        
    return {"status": "ok", "message": f"Successfully saved to {filename}"}