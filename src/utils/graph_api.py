import os
import json
from typing import Dict, Any
from src.utils.config import BASE_DIR


GRAPH_DIR = os.path.join(BASE_DIR, "src", "harness", "graph")
NODE_DIR = os.path.join(BASE_DIR, "src", "harness", "node")

os.makedirs(GRAPH_DIR, exist_ok=True)


def get_all_nodes():
    nodes = []
    if os.path.exists(NODE_DIR):
        for folder_name in os.listdir(NODE_DIR):
            folder_path = os.path.join(NODE_DIR, folder_name)
            if os.path.isdir(folder_path):
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


def list_graphs():
    files = []
    if os.path.exists(GRAPH_DIR):
        for f in os.listdir(GRAPH_DIR):
            if f.endswith(".json"):
                files.append({"name": f, "path": os.path.join(GRAPH_DIR, f)})
    return files


def get_graph(filename: str):
    filepath = os.path.join(GRAPH_DIR, filename)
    if not os.path.exists(filepath):
        filepath = os.path.join(GRAPH_DIR, f"{filename}.json")
        if not os.path.exists(filepath):
            return None
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def save_graph(filename: str, graph_data: Dict[str, Any]):
    if not filename.endswith(".json"):
        filename += ".json"
    filepath = os.path.join(GRAPH_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(graph_data, f, ensure_ascii=False, indent=2)
    return {"status": "ok", "message": f"Successfully saved to {filename}"}
