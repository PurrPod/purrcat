import os
import json
import importlib
from typing import List, Dict, Any
from .base import BaseNode


def get_all_node_schemas() -> List[Dict[str, Any]]:
    """扫描 node/ 下所有文件夹的 meta.json，一次性打包发给前端画图组件"""
    schemas = []
    base_dir = os.path.dirname(__file__)
    for item in os.listdir(base_dir):
        item_path = os.path.join(base_dir, item)
        if os.path.isdir(item_path) and not item.startswith('_'):
            meta_path = os.path.join(item_path, "meta.json")
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, 'r', encoding='utf-8') as f:
                        schema = json.load(f)
                        schemas.append(schema)
                except Exception as e:
                    print(f"⚠️ 加载节点 schema 失败 {item}: {e}")
    return schemas


def load_node_module(node_type: str):
    """动态加载指定类型的节点模块"""
    try:
        module = importlib.import_module(f"harness.node.{node_type}.node")
        return module.Node
    except Exception as e:
        print(f"❌ 加载节点模块失败 {node_type}: {e}")
        raise


def get_node_schema(node_type: str) -> Dict[str, Any]:
    """获取指定节点类型的 schema"""
    base_dir = os.path.dirname(__file__)
    meta_path = os.path.join(base_dir, node_type, "meta.json")
    if os.path.exists(meta_path):
        with open(meta_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None