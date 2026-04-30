"""MCP 获取模块 - 仅从本地 Schema 缓存文件读取，绝对不处理握手逻辑"""

from typing import List, Dict, Tuple
from .exceptions import MCPServerNotFoundError, MCPToolNotFoundError


def fetch_mcp_tools(server_name: str, tool_names: list = None) -> Tuple[List[Dict], None]:
    """
    纯本地读取 MCP Schema 缓存 (mcp_schema.jsonl)

    Args:
        server_name: MCP 服务器名称
        tool_names: 要获取的工具名称列表，为空则获取所有工具

    Returns:
        (schemas, None) 或抛出异常
    """
    try:
        from src.tool.callmcp.schema_manager import load_cached_schemas

        all_schemas = load_cached_schemas()

        available_servers = list(set([s.get("server") for s in all_schemas if s.get("server")]))

        if server_name not in available_servers:
            raise MCPServerNotFoundError(server_name, available_servers)

        server_schemas = [s for s in all_schemas if s.get("server") == server_name]
        available_tools = [s.get("function", {}).get("name") for s in server_schemas]

        if tool_names and isinstance(tool_names, list) and tool_names:
            schemas = []
            for schema in server_schemas:
                func_name = schema.get("function", {}).get("name")
                if func_name in tool_names:
                    schemas.append(schema)

            if not schemas:
                raise MCPToolNotFoundError(server_name, tool_names, available_tools)
        else:
            schemas = server_schemas

        return schemas, None

    except ImportError as e:
        return None, f"MCP 模块未安装: {str(e)}"
    except (MCPServerNotFoundError, MCPToolNotFoundError):
        raise
    except Exception as e:
        return None, f"MCP 缓存读取失败: {str(e)}"