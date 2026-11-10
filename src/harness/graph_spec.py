"""图定义加载、输入参数校验与节点实例构建。"""

from __future__ import annotations

import importlib
import json
import os

from .enums import NodeState


def load_graph_file(graphs_dir: str, graph_name: str) -> dict | None:
    """读取 graph.json；文件缺失时返回 None（保持原引擎的容错行为）。"""
    graph_path = os.path.join(graphs_dir, graph_name, "graph.json")
    if not os.path.exists(graph_path):
        return None
    with open(graph_path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_global_inputs(inputs: dict, global_schema: dict) -> str:
    """校验任务入参；返回错误文案，无错误返回空串。"""
    validation_errors = []

    missing_required = []
    for req_key, schema_info in global_schema.items():
        is_req = schema_info.get("required", True)
        if is_req and (req_key not in inputs or inputs[req_key] is None):
            missing_required.append(
                {
                    "name": req_key,
                    "type": schema_info.get("type", "any"),
                    "description": schema_info.get("description", "无特定说明"),
                    "required": True,
                }
            )

    if missing_required:
        param_list = "\n    - ".join(
            [
                f"'{p['name']}' (类型: {p['type']}, 描述: {p['description']})"
                for p in missing_required
            ]
        )
        validation_errors.append(f"❌ 缺少必填参数:\n    - {param_list}")

    extra_keys = [k for k in inputs.keys() if k not in global_schema]
    if extra_keys:
        extra_list = ", ".join([f"'{k}'" for k in extra_keys])
        validation_errors.append(f"⚠️ 传入了未知参数: {extra_list}")

    if not validation_errors:
        return ""

    all_params_info = []
    for key, schema_info in global_schema.items():
        is_req = schema_info.get("required", True)
        req_mark = "✅ 必填" if is_req else "⭕ 可选"
        all_params_info.append(
            f"    - '{key}' (类型: {schema_info.get('type', 'any')}, {req_mark}, "
            f"描述: {schema_info.get('description', '无特定说明')})"
        )

    error_msg = "\n".join(validation_errors)
    error_msg += "\n\n📋 有效的参数列表:\n" + "\n".join(all_params_info)
    error_msg += "\n\n💡 请检查您的输入参数后重试。"
    return error_msg


def build_node_instances(graph: dict) -> tuple[dict, dict, dict, str]:
    """按图定义构建节点实例。

    返回 (node_list, node_types, node_state, error)；error 为空串表示成功。
    """
    node_list = {}
    node_types = {}
    node_state = {}

    for node_data in graph.get("nodes", []):
        node_id = node_data["id"]
        node_type = node_data["type"]
        config = node_data.get("config", node_data.get("data", {}))

        try:
            module = importlib.import_module(
                f"src.harness.node.extensions.{node_type}.node"
            )
            node_list[node_id] = module.Node(node_id=node_id, config=config)
            node_types[node_id] = node_type
            node_state[node_id] = NodeState.READY
        except Exception as e:
            from src.utils.graph_api import DEPRECATED_NODE_TYPES

            if node_type in DEPRECATED_NODE_TYPES:
                return (
                    node_list,
                    node_types,
                    node_state,
                    f"节点类型 [{node_type}] 已在信封协议重构中移除，"
                    f"请用编辑器打开 graph 替换该节点（预览文件请改用 preview 节点，"
                    f"静态文本请改用 string 节点连线输入，"
                    f"数据组装/逻辑分流请交给 agent_loop）",
                )
            return (
                node_list,
                node_types,
                node_state,
                f"节点加载失败 [{node_type}]: {e}",
            )

    return node_list, node_types, node_state, ""
