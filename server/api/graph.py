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


@router.post("/{filename}")
def save_graph_api(filename: str, graph_data: Dict[str, Any]):
    return save_graph(filename, graph_data)
