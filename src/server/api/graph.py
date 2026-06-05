from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from src.utils.graph_api import get_all_nodes, get_graph, list_graphs, save_graph

router = APIRouter(prefix="/api/graphs", tags=["DAG Graphs"])


@router.get("/nodes")
def get_all_nodes_api():
    return get_all_nodes()


@router.get("")
def list_graphs_api():
    return list_graphs()


@router.get("/{filename}")
def get_graph_api(filename: str):
    result = get_graph(filename)
    if result is None:
        raise HTTPException(status_code=404, detail="Graph not found")
    return result


@router.get("/{filename}/schema")
def get_graph_schema_api(filename: str):
    """获取工作流的全局输入参数 Schema，前端可据此动态生成参数填写表单"""
    result = get_graph(filename)
    if result is None:
        raise HTTPException(status_code=404, detail="Graph not found")

    global_schema = result.get("global_schema", {})
    if not global_schema and "required_inputs" in result:
        global_schema = {
            k: {"required": True, "description": v}
            for k, v in result["required_inputs"].items()
        }

    return {
        "graph_name": filename,
        "global_schema": global_schema,
    }


@router.post("/{filename}")
def save_graph_api(filename: str, graph_data: Dict[str, Any]):
    return save_graph(filename, graph_data)
