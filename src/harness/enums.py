from enum import Enum


class TaskState(str, Enum):
    READY = "ready"
    STARTING = "starting"
    RUNNING = "running"
    INTERRUPTED = "interrupted"
    COMPLETED = "completed"
    ERROR = "error"
    KILLED = "killed"


class NodeState(str, Enum):
    READY = "ready"  # 初始状态或被重置
    WAITING = "waiting"  # Agent 被挂起，等待人工注入指令
    RUNNING = "running"  # 正在执行中
    ERROR = "error"  # 执行出错
    COMPLETED = "completed"  # 执行成功
    SKIPPED = "skipped"  # 因路由未命中，被上游短路跳过


class PortState(str, Enum):
    PENDING = "pending"  # 等待包裹投递
    HAS_DATA = "has_data"  # 已收到包裹
    VOID = "void"  # 空包裹/跳过信号（路由短路用）


class LogType(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    SYSTEM = "system"
    TOOL_CALL = "tool_call"
    TOOL = "tool"
    ARTIFACT = "artifact"
