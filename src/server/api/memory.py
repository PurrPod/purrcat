import os
import traceback
from fastapi import APIRouter, HTTPException, Body

from src.memory import (
    get_recent_events,
    get_recent_experiences,
    get_memory_graph,
    search_memory,
)

from src.memory.purrmemo.core.storage.vector_engine import VectorEngine
from src.memory.purrmemo.core.storage.event_engine import EventEngine
from src.memory.purrmemo.core.storage.graph_engine import GraphEngine

from src.utils.config import AGENT_CORE_DIR

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


@router.delete("/experiences/{exp_id}")
def delete_experience(exp_id: str):
    """删除工作经验 (VectorDB)"""
    try:
        engine = VectorEngine()
        if engine.delete_experience(exp_id):
            return {"status": "success", "message": "经验已删除"}
        raise HTTPException(status_code=404, detail="经验不存在")
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/events/{event_id}")
def delete_event(event_id: str):
    """删除事件 (SQLite + FTS5)"""
    try:
        engine = EventEngine()
        if engine.delete_event(event_id):
            return {"status": "success", "message": "事件已删除"}
        raise HTTPException(status_code=404, detail="事件不存在")
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/graph/relation")
def delete_relation(source_node_id: str, target_node_id: str):
    """物理删除图谱关系边"""
    try:
        engine = GraphEngine()
        if engine.delete_relation(source_node_id, target_node_id):
            return {"status": "success", "message": "关系边已删除"}
        raise HTTPException(status_code=404, detail="未找到该关系边")
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# 🌟 修改后：基于 AGENT_CORE_DIR 的 MEMORY.md 读写 API
# ==========================================


@router.get("/markdown")
def get_memory_markdown_api():
    """读取 .purrcat/core/MEMORY.md 文件内容"""
    try:
        # 🌟 路径切换为 AGENT_CORE_DIR
        file_path = os.path.join(AGENT_CORE_DIR, "MEMORY.md")
        if not os.path.exists(file_path):
            return {"content": ""}

        with open(file_path, "r", encoding="utf-8") as f:
            return {"content": f.read()}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"读取 MEMORY.md 失败: {str(e)}")


@router.put("/markdown")
def update_memory_markdown_api(payload: dict = Body(...)):
    """保存并覆盖写入 .purrcat/core/MEMORY.md 文件"""
    try:
        content = payload.get("content", "")
        # 🌟 路径切换为 AGENT_CORE_DIR
        file_path = os.path.join(AGENT_CORE_DIR, "MEMORY.md")

        # 确保父级目录 .purrcat/core 存在
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        return {"status": "success", "message": "MEMORY.md 已成功落盘保存"}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"保存 MEMORY.md 失败: {str(e)}")
