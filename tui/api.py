from src.agent import (
    agent_force_push,
    flush_agent_memory as flush_agent_memory_api,
    get_agent_max_token as get_agent_max_token_api,
    get_chat_history,
    get_session_list,
    get_window_token as get_window_token_api,
    branch_session,
    switch_session,
    get_active_session_id,
    new_session
)
from src.utils.log_api import format_task_log
from src.utils.task_api import (
    force_push_task,
    get_task_list,
    get_task_max_token,
    get_task_window_token,
)

__all__ = [
    "get_agent_history",
    "force_push_agent",
    "flush_agent_memory",
    "get_window_token",
    "get_agent_max_token",
    "get_session_list",
    "format_task_log",
    "get_task_list",
    "force_push_task",
    "get_task_max_token",
    "get_task_window_token",
    "get_active_session_id",
    "branch_session",
    "switch_session",
    "new_session",
]


def get_agent_history():
    try:
        return get_chat_history()
    except Exception:
        return []


def force_push_agent(text: str):
    agent_force_push(text, type="user")
    return True


def flush_agent_memory():
    return flush_agent_memory_api()


def get_window_token():
    return get_window_token_api()


def get_agent_max_token():
    return get_agent_max_token_api()
