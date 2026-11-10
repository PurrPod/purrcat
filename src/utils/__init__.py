"""
全局通用工具库，收口配置、日志、任务与图谱等底层 API
"""

from .config import (
    get_agent_model,
    get_data_dir,
    get_embedding_model,
    get_file_config,
    get_mcp_config,
    get_model_config,
    get_sensor_config,
)
from .log_api import clean_log_entry, format_task_log, get_task_log_structured
from .skill_helper import get_available_skills, get_skill_content, get_skill_info
from .tracker import Tracker

# 任务 API 依赖 harness，而 harness 又依赖 model；若在此立即导入，
# 全新进程 `import src.model` 会形成 utils → harness → model → utils 的循环。
_TASK_API_NAMES = {
    "delete_task",
    "force_push_task",
    "get_task_history",
    "get_task_list",
    "get_task_log_jsonl",
    "get_task_max_token",
    "get_task_state",
    "get_task_window_token",
    "kill_task",
    "submit_instruction",
}


def __getattr__(name):
    if name in _TASK_API_NAMES:
        from . import task_api

        return getattr(task_api, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Config
    "get_model_config",
    "get_sensor_config",
    "get_file_config",
    "get_mcp_config",
    "get_agent_model",
    "get_embedding_model",
    "get_data_dir",
    # Task API
    "get_task_list",
    "get_task_state",
    "get_task_log_jsonl",
    "kill_task",
    "submit_instruction",
    "delete_task",
    "get_task_history",
    "force_push_task",
    "get_task_window_token",
    "get_task_max_token",
    # Graph & Log API
    "get_task_log_structured",
    "format_task_log",
    "clean_log_entry",
    # Skills & Tracker
    "get_available_skills",
    "get_skill_content",
    "get_skill_info",
    "Tracker",
]
