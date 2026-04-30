"""MCP 搜索实现"""
from typing import List, Dict
import json


def mcp_search(query: str, max_results: int = 5) -> tuple:
    """
    通过遍历缓存的 MCP Schema，寻找名称或描述中匹配查询的工具。
    不包括参数的匹配，避免被复杂的参数字段干扰。
    """
    results = []
    error_logs = []

    try:
        from src.tool.callmcp.schema_manager import load_cached_schemas
        schemas = load_cached_schemas()

        query_lower = query.lower()
        scored_results = []

        for schema in schemas:
            server_name = schema.get("server", "")
            func = schema.get("function", {})
            tool_name = func.get("name", "")
            description = func.get("description", "")

            # 仅根据工具名称和描述进行匹配（不包括 parameters）
            search_text = f"{tool_name} {description}".lower()

            score = 0
            if query_lower in tool_name.lower():
                score += 10
            if query_lower in description.lower():
                score += 5

            # 按词匹配
            query_words = query_lower.split()
            for word in query_words:
                if word and word in search_text:
                    score += 1

            if score > 0:
                scored_results.append({
                    "score": score,
                    "server_name": server_name,
                    "tool_name": tool_name,
                    "description": description
                })

        # 排序并提取 TopK
        scored_results.sort(key=lambda x: x["score"], reverse=True)

        for item in scored_results[:max_results]:
            results.append({
                "server_name": item["server_name"],
                "tool_name": item["tool_name"],
                "description": item["description"]
            })

        return results, None

    except Exception as e:
        error_logs.append(f"MCP搜索异常: {str(e)}")
        return [], f"MCP搜索失败: {', '.join(error_logs)}"