class FetchExecutionError(Exception):
    """基础的 Fetch 异常"""
    pass


class SkillNotFoundError(FetchExecutionError):
    """技能未找到异常"""
    def __init__(self, name: str):
        self.name = name
        super().__init__(f"未找到技能: {name}")


class MCPServerNotFoundError(FetchExecutionError):
    """MCP 服务器未找到异常"""
    def __init__(self, serve_name: str, available_servers: list):
        self.serve_name = serve_name
        self.available_servers = available_servers
        super().__init__(f"未找到 MCP 服务器: {serve_name}")


class MCPToolNotFoundError(FetchExecutionError):
    """MCP 工具未找到异常"""
    def __init__(self, serve_name: str, tool_names: list, available_tools: list):
        self.serve_name = serve_name
        self.tool_names = tool_names
        self.available_tools = available_tools
        super().__init__(f"MCP 服务器 {serve_name} 中未找到工具")


class WebNetworkError(FetchExecutionError):
    """Web 抓取网络异常"""
    pass