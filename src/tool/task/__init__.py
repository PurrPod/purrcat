"""
与后台子任务的交互接口，包括 add，kill，list
"""

from .schema import TASK_TOOL_SCHEMA
from .task import Task

__all__ = ["Task", "TASK_TOOL_SCHEMA"]
