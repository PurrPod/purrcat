from enum import Enum


class TaskState(str, Enum):
    """任务生命周期状态"""
    READY = "ready"
    STARTING = "starting"    # 防止并发注入的中间态
    RUNNING = "running"
    INTERRUPTED = "interrupted"
    COMPLETED = "completed"
    ERROR = "error"
    KILLED = "killed"


class LogType(str, Enum):
    """前端展示/日志卡片类型"""
    SYSTEM = "system"
    THOUGHT = "thought"
    TOOL_CALL = "tool_call"
    TOOL = "tool"
    WARNING = "warning"
    ERROR = "error"