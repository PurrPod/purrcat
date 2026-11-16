"""
调用 mcp 工具，为系统提供初始化功能。

保持轻量：fetch/search 只需要 schema_manager 的缓存读取能力，
不应因为访问本包而 eager 拉起完整 MCP 客户端（约 1s 的 mcp SDK 导入）。
"""

__all__ = ["CallMCP", "initialize_mcp_sync", "reload_mcp_schema", "MCP_TOOL_SCHEMA"]

_LAZY_EXPORTS = {
    "CallMCP": (".callmcp", "CallMCP"),
    "initialize_mcp_sync": (".callmcp", "initialize_mcp_sync"),
    "reload_mcp_schema": (".callmcp", "reload_mcp_schema"),
    "MCP_TOOL_SCHEMA": (".schema", "MCP_TOOL_SCHEMA"),
}


def __getattr__(name):
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr = _LAZY_EXPORTS[name]
    from importlib import import_module

    value = getattr(import_module(module_name, __name__), attr)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__))
