import os
import json
from typing import List, Optional, Any

_retriever_instance: Optional[Any] = None


def _get_retriever() -> Any:
    global _retriever_instance
    if _retriever_instance is None:
        from src.loader.rag import RAGRetriever
        # 仅仅实例化对象，不加载任何数据库，实现真正的懒加载
        _retriever_instance = RAGRetriever(base_dir="data/database")
    return _retriever_instance


def _format_response(msg_type: str, content: Any) -> str:
    return json.dumps({"type": msg_type, "content": content}, ensure_ascii=False)


def list_databases() -> str:
    """提供给大模型：只返回存在的数据库名称，不加载数据"""
    base_dir = "data/database"
    if not os.path.exists(base_dir):
        return _format_response("text", {"available_databases": []})

    available_dbs = [d for d in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, d))]
    return _format_response("text", {"available_databases": available_dbs})


def rag_search(query: str, target_dbs: List[str], top_k: int = 3) -> str:
    """提供给大模型：在指定的数据库中进行 RAG 搜索"""
    if not target_dbs:
        return _format_response("error",
                                "You must specify at least one database in 'target_dbs'. Use 'list_databases' if you don't know the names.")

    try:
        retriever = _get_retriever()
        results = retriever.search(query=query, target_dbs=target_dbs, top_k=top_k)

        if not results:
            return _format_response("text", f"No relevant information found in databases: {target_dbs}.")

        formatted_results = []
        for res in results:
            source = res['meta'].get('source', 'unknown')
            chunk_id = res['meta'].get('chunk_id', -1)
            text = res['text']
            db_name = res['db_name']

            chunk_info = f"[库: {db_name}] [文件: {source}] [Chunk ID: {chunk_id}]\n{text}"
            formatted_results.append(chunk_info)

        return _format_response("text", "\n\n---\n\n".join(formatted_results))

    except Exception as e:
        return _format_response("error", f"Search failed: {str(e)}")


def expand_database_context(db_name: str, source: str, center_chunk_id: int, window: int = 1) -> str:
    """扩展特定数据库片段的上下文"""
    try:
        retriever = _get_retriever()
        expanded_text = retriever.expand_context(
            db_name=db_name,
            source=source,
            center_chunk_id=center_chunk_id,
            window=window
        )
        if not expanded_text:
            return _format_response("error", "No expanded context found.")

        return _format_response("text", f"=== 扩展上下文 (Window ±{window}) ===\n{expanded_text}")
    except Exception as e:
        return _format_response("error", f"Expand context failed: {str(e)}")