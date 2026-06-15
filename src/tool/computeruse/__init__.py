"""
ComputerUse 工具 - 跨平台物理计算机控制工具
允许 AI 像人类一样查看屏幕、移动鼠标、点击和打字
"""

from .schema import COMPUTERUSE_TOOL_SCHEMA
from .computeruse import ComputerUse

__all__ = ["COMPUTERUSE_TOOL_SCHEMA", "ComputerUse"]
