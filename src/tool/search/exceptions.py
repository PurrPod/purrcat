"""Search 工具异常类"""


class SearchError(Exception):
    """搜索操作基类异常"""
    pass


class InvalidRouteError(SearchError):
    """无效的路由类型"""
    def __init__(self, route: str):
        super().__init__(f"无效的路由类型: {route}。支持的路由: web, skill, mcp")


class MissingParameterError(SearchError):
    """缺少必需参数"""
    def __init__(self, param_name: str):
        super().__init__(f"缺少必需参数: {param_name}")


class SearchFailedError(SearchError):
    """搜索失败"""
    def __init__(self, route: str, reason: str):
        super().__init__(f"{route} 搜索失败: {reason}")


class SkillNotFoundError(SearchError):
    """技能未找到"""
    def __init__(self, name: str):
        super().__init__(f"找不到技能: {name}")