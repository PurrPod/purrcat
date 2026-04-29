class FetchExecutionError(Exception):
    """基础的 Fetch 异常"""
    pass


class SkillNotFoundError(FetchExecutionError):
    """技能未找到异常"""
    def __init__(self, name: str):
        self.name = name
        super().__init__(f"未找到技能: {name}")


class MCPNotFoundError(FetchExecutionError):
    """MCP 工具未找到异常"""
    def __init__(self, serve_name: str, tool_names: str | list | None = None):
        self.serve_name = serve_name
        # 格式化 tool_names 方便话术展示
        self.tool_names = tool_names if tool_names else "相关"
        super().__init__(f"未找到 MCP 工具: {serve_name}")


class WebNetworkError(FetchExecutionError):
    """Web 抓取网络异常"""
    pass