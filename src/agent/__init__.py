"""
Agent 系统网关 (Facade)
实例化 AgentManager 并对外提供 10 大核心操作接口。
所有外部交互必须通过此处的暴露函数进行。
"""

from .manager import AgentManager

# ==========================================
# 1. 核心实例化 (仅在 __init__ 被加载时执行一次)
# ==========================================
_manager_instance = AgentManager()

# ==========================================
# 2. 方法提取与包装
# ==========================================
# 生命周期
init_agent = _manager_instance.init_agent
shutdown_agent = _manager_instance.shutdown_agent

# 交互指令
agent_force_push = _manager_instance.agent_force_push

# 会话控制
switch_session = _manager_instance.switch_session
new_session = _manager_instance.new_session
branch_session = _manager_instance.branch_session
delete_session = _manager_instance.delete_session

# 数据获取
get_chat_history = _manager_instance.get_chat_history
get_session_list = _manager_instance.get_session_list
get_active_session_id = _manager_instance.get_active_session_id


# 状态与辅助
def get_agent_status():
    return {
        "state": _manager_instance._agent.state
        if getattr(_manager_instance, "_agent", None)
        else "idle",
        "session_id": _manager_instance._agent.session_id
        if getattr(_manager_instance, "_agent", None)
        else None,
        "window_token": _manager_instance._agent.window_token
        if getattr(_manager_instance, "_agent", None)
        else 0,
    }


def flush_agent_memory():
    if getattr(_manager_instance, "_agent", None) is None:
        _manager_instance.init_agent()
    if getattr(_manager_instance, "_agent", None):
        _manager_instance._agent.force_compress_memory()
        return True
    return False


def get_window_token():
    if getattr(_manager_instance, "_agent", None) is None:
        _manager_instance.init_agent()
    return (
        _manager_instance._agent.window_token
        if getattr(_manager_instance, "_agent", None)
        else 0
    )


def get_agent_max_token():
    return 1000000


# ==========================================
# 3. 严格限制导出接口
# ==========================================
__all__ = [
    "init_agent",
    "shutdown_agent",
    "agent_force_push",
    "switch_session",
    "new_session",
    "branch_session",
    "delete_session",
    "get_chat_history",
    "get_session_list",
    "get_active_session_id",
    "get_agent_status",
    "flush_agent_memory",
    "get_window_token",
    "get_agent_max_token",
]
