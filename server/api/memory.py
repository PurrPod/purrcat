import traceback
from fastapi import APIRouter
from src.memory.purrmemo.core.storage.event_engine import EventEngine
from src.memory.purrmemo.core.storage.vector_engine import VectorEngine
from src.memory.purrmemo.core.storage.graph_engine import GraphEngine
from src.memory.purrmemo.client import get_memory_client

router = APIRouter(prefix="/api/memory", tags=["Memory System"])

@router.get("/events")
def get_recent_events():
    try:
        return EventEngine().get_events(limit=30)
    except Exception:
        return []

@router.get("/experiences")
def get_recent_experiences():
    try:
        engine = VectorEngine()
        if not engine.collection:
            return []
        results = engine.collection.get(include=["documents", "metadatas"])
        experiences = []
        if results and results.get("ids"):
            for i in range(len(results["ids"])):
                meta = results["metadatas"][i] or {}
                experiences.append({
                    "exp_id": results["ids"][i],
                    "content": results["documents"][i],
                    "timestamp": meta.get("timestamp", "")
                })
        experiences.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return experiences[:30]
    except Exception:
        return []

# 🌟 全量图谱获取接口
@router.get("/graph")
def get_full_cognition_graph():
    try:
        engine = GraphEngine()
        if not engine.graph:
            return {"nodes": [], "edges": []}

        nodes = []
        edges = []
        
        # 1. 全量提取所有节点
        for node_id in engine.graph.nodes:
            data = engine.graph.nodes[node_id]
            nodes.append({
                "id": node_id, 
                "label": data.get("name", node_id)
            })

        # 2. 全量提取所有边关系
        for source, target, edge_data in engine.graph.edges(data=True):
            edges.append({
                "from": source,
                "to": target,
                "label": edge_data.get("relation_meaning", "未知关系"),
                "confidence": edge_data.get("confidence", 0.5),
                "updated_at": edge_data.get("updated_at", "")
            })
            
        return {"nodes": nodes, "edges": edges}
    except Exception:
        traceback.print_exc()
        return {"nodes": [], "edges": []}

@router.get("/search")
def search_memory(q: str = ""):
    if not q:
        return {"result": ""}
    try:
        return {"result": get_memory_client().search(query=q)}
    except Exception as e:
        return {"result": f"搜索失败: {e}"}