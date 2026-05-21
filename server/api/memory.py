import traceback
from fastapi import APIRouter
from src.memory import (
    get_recent_events,
    get_recent_experiences,
    get_memory_graph,
    search_memory,
)

router = APIRouter(prefix="/api/memory", tags=["Memory System"])


@router.get("/events")
def get_events():
    try:
        return get_recent_events(limit=30)
    except Exception:
        return []


@router.get("/experiences")
def get_experiences():
    try:
        return get_recent_experiences(limit=30)
    except Exception:
        return []


@router.get("/graph")
def get_graph():
    try:
        return get_memory_graph()
    except Exception:
        traceback.print_exc()
        return {"nodes": [], "edges": []}


@router.get("/search")
def search(q: str = ""):
    if not q:
        return {"result": ""}
    try:
        return {"result": search_memory(query=q)}
    except Exception as e:
        return {"result": f"搜索失败: {e}"}
