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
agent_force_push_batch = _manager_instance.agent_force_push_batch
agent_force_interrupt = _manager_instance.agent_force_interrupt

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
        "compressing": getattr(_manager_instance._agent, "_compressing", False)
        if getattr(_manager_instance, "_agent", None)
        else False,
        # 🌟 流式思考内容（仅活跃会话思考期间非空，供前端实时渲染）
        "live_reasoning": getattr(_manager_instance._agent, "_live_reasoning", "")
        if getattr(_manager_instance, "_agent", None)
        else "",
        # 🌟 当前交互阶段：thinking=模型推理中 / processing=工具执行中 / idle=空闲
        "live_phase": getattr(_manager_instance._agent, "_live_phase", "idle")
        if getattr(_manager_instance, "_agent", None)
        else "idle",
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
    """上下文窗口上限：跟随当前模型配置里的 max_token。

    原先这里写死 1000000，与 Agent 自身的记忆截断口径（model.json 的
    main.<模型>.max_token，默认 500000）不一致，导致前端圆环显示错误。
    """
    model_name = getattr(getattr(_manager_instance, "_agent", None), "name", None)
    if not model_name:
        return 500000

    from src.utils.config import get_model_config

    model_cfg = get_model_config().get("main", {}).get(model_name, {})
    return model_cfg.get("max_token", 500000)


# ==========================================
# 3. 严格限制导出接口
# ==========================================
__all__ = [
    "init_agent",
    "shutdown_agent",
    "agent_force_push",
    "agent_force_push_batch",
    "agent_force_interrupt",
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
