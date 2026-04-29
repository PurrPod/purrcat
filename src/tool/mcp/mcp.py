"""MCP 工具主入口 - 统一调度 MCP 工具调用"""

import threading
import traceback
from src.tool.utils.format import text_response, error_response, warning_response
from src.tool.mcp.exceptions import (
    MCPError,
    InvalidActionError,
    MissingParameterError,
    ServerNotFoundError
)
from src.tool.mcp.tool_caller import call_mcp_tool, list_mcp_tools
from src.tool.mcp.schema_manager import load_cached_schemas, refresh_schemas


def CallMCP(action: str, server_name: str = None, tool_name: str = None, 
            arguments: dict = None, **kwargs) -> str:
    """
    MCP 工具主入口函数，支持三种操作：call、list、schemas
    
    Args:
        action: 操作类型，必须为 "call"（调用工具）、"list"（获取工具列表）或 "schemas"（获取 Schema）
        server_name: MCP Server 名称（call 和 list 操作时必填）
        tool_name: 工具名称（call 操作时必填）
        arguments: 工具参数（call 操作时使用）
    
    Returns:
        格式化后的 JSON 字符串，包含 timestamp, type, content, snip
    """
    try:
        # 参数校验
        action = action.strip().lower() if action else ""
        
        # 检查操作类型
        if action not in ["call", "list", "schemas"]:
            return error_response(
                f"无效的操作类型: {action}。支持的操作: call, list, schemas",
                "参数错误"
            )
        
        # 根据操作类型执行相应逻辑
        if action == "schemas":
            # schemas 操作：获取所有缓存的 Schema
            try:
                if server_name:
                    # 获取指定 Server 的 Schema
                    schemas = [s for s in load_cached_schemas() if s.get("server") == server_name]
                    snip = f"获取 {server_name} 的 {len(schemas)} 个 Schema"
                else:
                    # 获取所有 Schema
                    schemas = load_cached_schemas()
                    snip = f"获取所有 {len(schemas)} 个 Schema"
                return text_response(schemas, snip)
            except MCPError as e:
                return error_response(str(e), "获取 Schema 失败")
        
        elif action == "list":
            # list 操作：获取工具列表
            if not server_name or not server_name.strip():
                return error_response("list 操作需要提供 server_name（MCP Server 名称）", "参数错误")
            
            try:
                tools = list_mcp_tools(server_name)
                snip = f"{server_name} 共有 {len(tools)} 个工具"
                return text_response(tools, snip)
            except MCPError as e:
                return error_response(str(e), "获取工具列表失败")
        
        elif action == "call":
            # call 操作：调用工具
            if not server_name or not server_name.strip():
                return error_response("call 操作需要提供 server_name（MCP Server 名称）", "参数错误")
            
            if not tool_name or not tool_name.strip():
                return error_response("call 操作需要提供 tool_name（工具名称）", "参数错误")
            
            args = arguments or {}
            # 处理大模型可能传入 JSON 字符串的情况
            if isinstance(args, str):
                import json
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    return error_response("arguments 必须是有效的 JSON 字典对象，请勿传入无法解析的字符串格式。", "参数类型错误")
            
            try:
                result = call_mcp_tool(server_name, tool_name, args)
                snip = f"调用 {server_name}.{tool_name} 成功"
                return text_response(result, snip)
            except ServerNotFoundError as e:
                return error_response(str(e), "服务器未找到")
            except MCPError as e:
                return warning_response(str(e), "调用失败")
        
        return error_response("未知错误", "系统错误")
        
    except Exception as e:
        # 【关键】捕获所有异常，格式化为模型可读的错误，而不是让程序崩溃
        traceback.print_exc()
        return error_response(f"MCP 运行时异常: {str(e)}", "执行失败")


def initialize_mcp():
    """初始化 MCP 系统（异步预加载 Schema 缓存，防止阻塞 Agent 启动）"""
    print("🔄 [MCP] 触发后台初始化...")
    
    def _bg_init():
        try:
            schemas = load_cached_schemas()
            print(f"✅ [MCP] 初始化完成，已加载 {len(schemas)} 个工具 Schema")
        except Exception as e:
            print(f"⚠️ [MCP] 初始化失败: {e}")
    
    # 使用后台守护线程执行初始化，防止网络问题导致 Agent 启动卡死
    thread = threading.Thread(target=_bg_init, daemon=True)
    thread.start()
    return True


def refresh_mcp_schemas():
    """刷新 MCP Schema 缓存"""
    try:
        schemas = refresh_schemas()
        return text_response({"message": f"Schema 刷新成功，共 {len(schemas)} 个"}, "刷新成功")
    except Exception as e:
        traceback.print_exc()
        return error_response(str(e), "刷新失败")