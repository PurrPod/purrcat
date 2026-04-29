"""Task 工具异常类"""


class TaskError(Exception):
    """任务操作基类异常"""
    pass


class InvalidActionError(TaskError):
    """无效的操作类型"""
    def __init__(self, action: str):
        super().__init__(f"无效的操作类型: {action}。支持的操作: add, inform, kill, list")


class MissingParameterError(TaskError):
    """缺少必需参数"""
    def __init__(self, param_name: str):
        super().__init__(f"缺少必需参数: {param_name}")


class TaskNotFoundError(TaskError):
    """任务未找到"""
    def __init__(self, task_id: str):
        super().__init__(f"未找到任务: {task_id}")


class TaskCreateError(TaskError):
    """任务创建失败"""
    def __init__(self, reason: str):
        super().__init__(f"任务创建失败: {reason}")


class TaskKillError(TaskError):
    """任务终止失败"""
    def __init__(self, task_id: str, reason: str = ""):
        super().__init__(f"任务终止失败: {task_id}" + (f"，原因: {reason}" if reason else ""))