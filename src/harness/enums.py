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
    READY = "ready"         # 初始状态
    WAITING = "waiting"     # 被人类打回或上游重置，等待/准备重新执行
    RUNNING = "running"     # 正在执行中
    ERROR = "error"         # 节点抛出异常，挂起等待干预
    COMPLETED = "completed" # 执行成功

class LogType(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    SYSTEM = "system"
    TOOL_CALL = "tool_call"
    TOOL = "tool"