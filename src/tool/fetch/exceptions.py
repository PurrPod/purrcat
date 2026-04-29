"""Fetch 工具异常类"""


class FetchError(Exception):
    """获取操作基类异常"""
    pass


class InvalidSourceError(FetchError):
    """无效的来源类型"""
    def __init__(self, source: str):
        super().__init__(f"无效的来源类型: {source}。支持的来源: web, skill, mcp")


class MissingParameterError(FetchError):
    """缺少必需参数"""
    def __init__(self, param_name: str):
        super().__init__(f"缺少必需参数: {param_name}")


class FetchFailedError(FetchError):
    """获取失败"""
    def __init__(self, source: str, reason: str):
        super().__init__(f"{source} 获取失败: {reason}")


class SkillNotFoundError(FetchError):
    """技能未找到"""
    def __init__(self, name: str):
        super().__init__(f"找不到技能: {name}")


class MCPNotFoundError(FetchError):
    """MCP 服务器未找到"""
    def __init__(self, server_name: str):
        super().__init__(f"找不到 MCP 服务器: {server_name}")