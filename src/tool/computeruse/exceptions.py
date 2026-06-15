"""ComputerUse 工具异常类"""


class ComputerUseError(Exception):
    """ComputerUse 操作基类异常"""

    pass


class UnsupportedPlatformError(ComputerUseError):
    """不支持的操作系统"""

    def __init__(self, platform_name: str):
        super().__init__(f"当前操作系统不支持此原生操作: {platform_name}")


class MissingParameterError(ComputerUseError):
    """缺少必需参数"""

    def __init__(self, param_name: str, action: str):
        super().__init__(f"操作 '{action}' 缺少必需参数: {param_name}")


class ExecutionFailedError(ComputerUseError):
    """底层动作执行失败"""

    def __init__(self, action: str, reason: str):
        super().__init__(f"操作 '{action}' 执行失败: {reason}")
