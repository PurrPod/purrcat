"""MCP 搜索模块 - 通过 MCP 服务器进行搜索"""

from typing import List, Dict


def mcp_search(query: str, max_results: int = 5) -> tuple:
    """
    通过 MCP 服务器进行搜索
    
    Args:
        query: 搜索查询词
        max_results: 最大返回结果数
    
    Returns:
        (results, error_message)
    """
    results = []
    error_logs = []
    
    try:
        from src.tool.mcp import CallMCP
        
        # 尝试调用 MCP 服务器的搜索工具
        # 这里需要根据实际的 MCP 服务器配置来调用
        result = CallMCP(
            action="list",
            server_name="search"  # 假设有一个名为 search 的 MCP 服务器
        )
        
        import json
        result_data = json.loads(result)
        
        if result_data.get("type") == "text":
            tools = result_data.get("content", [])
            # 查找搜索相关的工具并调用
            for tool in tools:
                if "search" in tool.get("name", "").lower():
                    search_result = CallMCP(
                        action="call",
                        server_name="search",
                        tool_name=tool["name"],
                        arguments={"query": query, "max_results": max_results}
                    )
                    search_data = json.loads(search_result)
                    if search_data.get("type") == "text":
                        results.extend(search_data.get("content", []))
        
        if results:
            return results[:max_results], None
        
    except ImportError:
        error_logs.append("MCP 模块未安装")
    except Exception as e:
        error_logs.append(f"MCP 搜索异常: {str(e)}")
    
    return [], f"MCP 搜索不可用: {', '.join(error_logs)}"