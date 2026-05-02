"""Memo 工具异常类"""


class MemoError(Exception):
    """Memo 操作基类异常"""
    pass


class MissingParameterError(MemoError):
    """缺少必需参数"""
    def __init__(self, param_name: str):
        super().__init__(f"缺少必需参数: {param_name}")


class InvalidParameterError(MemoError):
    """参数无效"""
    def __init__(self, param_name: str, reason: str):
        super().__init__(f"参数 '{param_name}' 无效: {reason}")