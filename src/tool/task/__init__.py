"""
与后台子任务的交互接口，包括inform和add，kill，list
"""

from .task import Task
from .schema import TASK_TOOL_SCHEMA

__all__ = ["Task", "TASK_TOOL_SCHEMA"]