import traceback
from fastapi import APIRouter
from src.memory import (
    search_memory as memory_search,
    get_memory_graph,
    get_recent_events,
    get_recent_experiences,
)

router = APIRouter(prefix="/api/memory", tags=["Memory System"])

@router.get("/events")
def events_endpoint():
    try:
        return get_recent_events(limit=30)
    except Exception:
        return []

@router.get("/experiences")
def experiences_endpoint():
    try:
        return get_recent_experiences(limit=30)
    except Exception:
        return []

# 🌟 全量图谱获取接口
@router.get("/graph")
def get_full_cognition_graph():
    try:
        return get_memory_graph()
    except Exception:
        traceback.print_exc()
        return {"nodes": [], "edges": []}

@router.get("/search")
def search_memory(q: str = ""):
    if not q:
        return {"result": ""}
    try:
        return {"result": memory_search(query=q)}
    except Exception as e:
        return {"result": f"搜索失败: {e}"}