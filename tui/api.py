from src.utils.log_api import clean_log_entry, format_task_log
from src.utils.task_api import (
    get_task_list, get_task_history, force_push_task,
    get_task_max_token, get_task_window_token, get_task_log_jsonl
)
from src.utils.session_api import (
    list_sessions, get_current_session_id, branch_session,
    checkout_session, new_clean_session
)
from src.agent.manager import get_agent


def get_agent_history():
    agent = get_agent()
    try:
        return agent.get_history()
    except Exception:
        return []


def force_push_agent(text: str):
    agent = get_agent()
    agent.force_push(text, type="user")
    return True


def flush_agent_memory():
    agent = get_agent()
    agent._check_and_summarize_memory(check_mode=False)
    return True


def get_window_token():
    agent = get_agent()
    return agent.window_token


def get_agent_max_token():
    return 1000000


def get_session_list():
    return list_sessions()
