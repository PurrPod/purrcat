"""
工具返回格式化与路由调度核心。

格式化函数保持 eager（各工具高频使用）；路由分发按需加载，
避免子进程仅需要 format 时也拉起 execution/media 等重链路。
"""

from .format import (
    error_response,
    format_tool_response,
    text_response,
    warning_response,
)

__all__ = [
    "format_tool_response",
    "text_response",
    "warning_response",
    "error_response",
    "dispatch_tool",
]


def __getattr__(name):
    if name != "dispatch_tool":
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from .route import dispatch_tool

    globals()["dispatch_tool"] = dispatch_tool
    return dispatch_tool


def __dir__():
    return sorted(set(globals()) | set(__all__))
