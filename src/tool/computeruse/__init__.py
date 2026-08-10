"""
ComputerUse 工具 - 跨平台物理计算机控制工具
允许 AI 像人类一样查看屏幕、移动鼠标、点击和打字
"""

from .schema import COMPUTERUSE_TOOL_SCHEMA
from .computeruse import ComputerUse
from .app_scanner import scan_desktop_apps, scan_and_save, generate_app_config

__all__ = [
    "COMPUTERUSE_TOOL_SCHEMA",
    "ComputerUse",
    "scan_desktop_apps",
    "scan_and_save",
    "generate_app_config",
]
