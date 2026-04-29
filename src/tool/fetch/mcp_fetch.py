"""MCP 获取模块 - 从缓存文件获取工具 Schema（避免反复握手）"""

from typing import List, Dict
from .exceptions import MCPNotFoundError


def fetch_mcp_tools(server_name: str, tool_names: list = None) -> tuple:
    """
    从缓存文件获取 MCP 工具 Schema（避免反复与服务器握手）
    
    Args:
        server_name: MCP 服务器名称
        tool_names: 要获取的工具名称列表，为空则获取所有工具
    
    Returns:
        (schemas, error_message)
    """
    try:
        from src.tool.mcp.schema_manager import get_server_schemas
        
        # 直接从缓存获取指定服务器的所有 Schema
        all_server_schemas = get_server_schemas(server_name)
        
        if not all_server_schemas:
            # 抛出 MCP 未找到异常
            raise MCPNotFoundError(server_name, tool_names)
        
        # 如果指定了工具名称列表，进行过滤
        if tool_names and isinstance(tool_names, list) and tool_names:
            schemas = []
            for schema in all_server_schemas:
                func_name = schema.get("function", {}).get("name")
                if func_name in tool_names:
                    schemas.append(schema)
            
            # 如果过滤后没有找到匹配的工具，也抛出异常
            if not schemas:
                raise MCPNotFoundError(server_name, tool_names)
        else:
            schemas = all_server_schemas
        
        return schemas, None
        
    except ImportError as e:
        return None, f"MCP 模块未安装: {str(e)}"
    except MCPNotFoundError:
        # 重新抛出，让上层捕获
        raise
    except Exception as e:
        return None, f"MCP 获取失败: {str(e)}"