"""FileSystem 工具异常类"""


class FileSystemError(Exception):
    """文件系统操作基类异常"""
    pass


class InvalidActionError(FileSystemError):
    """无效的操作类型"""
    def __init__(self, action: str):
        super().__init__(f"无效的操作类型: {action}。支持的操作: import, export, list")


class MissingParameterError(FileSystemError):
    """缺少必需参数"""
    def __init__(self, param_name: str, action: str = None):
        action_text = f"（操作: {action}）" if action else ""
        super().__init__(f"缺少必需参数: {param_name}{action_text}")


class InvalidParameterError(FileSystemError):
    """参数无效"""
    def __init__(self, param_name: str, reason: str):
        super().__init__(f"参数 '{param_name}' 无效: {reason}")


class PathNotFoundError(FileSystemError):
    """路径不存在"""
    def __init__(self, path: str, path_type: str = "路径"):
        super().__init__(f"{path_type}不存在: {path}")


class PermissionDeniedError(FileSystemError):
    """权限不足"""
    def __init__(self, path: str, reason: str = ""):
        msg = f"禁止访问路径: {path}"
        if reason:
            msg += f"\n原因: {reason}"
        super().__init__(msg)


class FileTooLargeError(FileSystemError):
    """文件过大"""
    def __init__(self, path: str, size_mb: float, max_mb: float = 30):
        super().__init__(f"文件过大 ({size_mb:.1f}MB)，超过 {max_mb}MB 限制: {path}")


class DirectoryTooLargeError(FileSystemError):
    """目录过大"""
    def __init__(self, path: str):
        super().__init__(f"目录过大 (超过 30MB)，禁止导入: {path}\n请只导入需要的文件")


class UnsupportedPathTypeError(FileSystemError):
    """不支持的路径类型"""
    def __init__(self, path: str):
        super().__init__(f"不支持的路径类型: {path}")


class GitNotAvailableError(FileSystemError):
    """Git 工具不可用"""
    def __init__(self):
        super().__init__(
            "本地未安装 git 工具，禁止导出以保护文件安全。\n"
            "请安装 git 后重试，或手动复制文件。"
        )