"""MCP 工具异常类"""


class MCPError(Exception):
    """MCP 操作基类异常"""
    pass


class InvalidActionError(MCPError):
    """无效的操作类型"""
    def __init__(self, action: str):
        super().__init__(f"无效的操作类型: {action}。支持的操作: call, list, schemas")


class MissingParameterError(MCPError):
    """缺少必需参数"""
    def __init__(self, param_name: str, action: str = None):
        action_text = f"（操作: {action}）" if action else ""
        super().__init__(f"缺少必需参数: {param_name}{action_text}")


class ServerNotFoundError(MCPError):
    """MCP Server 未配置"""
    def __init__(self, server_name: str):
        super().__init__(f"未知的 MCP Server: {server_name}")


class ToolNotFoundError(MCPError):
    """工具未找到"""
    def __init__(self, tool_name: str, server_name: str = None):
        server_text = f"（服务器: {server_name}）" if server_name else ""
        super().__init__(f"找不到工具: {tool_name}{server_text}")


class ServerConnectionError(MCPError):
    """服务器连接失败"""
    def __init__(self, server_name: str, reason: str = ""):
        msg = f"无法连接到 MCP Server: {server_name}"
        if reason:
            msg += f"\n原因: {reason}"
        super().__init__(msg)


class ServerTimeoutError(MCPError):
    """服务器启动超时"""
    def __init__(self, server_name: str, timeout: int = 120):
        super().__init__(f"MCP Server '{server_name}' 启动超时 ({timeout}s)")


class ToolExecutionError(MCPError):
    """工具执行错误"""
    def __init__(self, tool_name: str, error_msg: str):
        super().__init__(f"工具 '{tool_name}' 执行错误: {error_msg}")