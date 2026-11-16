"""
工具总入口，对外暴露路由、Schema、热更新接口和异步初始化方法。

包初始化保持轻量：隔离工具在子进程中只会 import 自己，不能因为父包
eager import 全部工具而额外背上数秒的解释器启动开销。
"""

import importlib
import threading

# --- 暴露的两套 Schema 列表（首次访问时再构建） ---

_SCHEMA_GROUPS = {
    "AGENT_TOOL_SCHEMA": (
        ("bash", "BASH_TOOL_SCHEMA"),
        ("brainstorm", "BRAINSTORM_TOOL_SCHEMA"),
        ("cron", "CRON_TOOL_SCHEMA"),
        ("fetch", "FETCH_TOOL_SCHEMA"),
        ("filesystem", "FILESYSTEM_TOOL_SCHEMA"),
        ("memo", "MEMO_TOOL_SCHEMA"),
        ("request", "REQUEST_TOOL_SCHEMA"),
        ("search", "SEARCH_TOOL_SCHEMA"),
        ("task", "TASK_TOOL_SCHEMA"),
        ("callmcp", "MCP_TOOL_SCHEMA"),
        ("kernelupgrade", "KERNELUPGRADE_TOOL_SCHEMA"),
    ),
    "BASE_TASK_TOOL_SCHEMA": (
        ("bash", "BASH_TOOL_SCHEMA"),
        ("filesystem", "FILESYSTEM_TOOL_SCHEMA"),
        ("search", "SEARCH_TOOL_SCHEMA"),
        ("callmcp", "MCP_TOOL_SCHEMA"),
        ("fetch", "FETCH_TOOL_SCHEMA"),
    ),
}

_LAZY_EXPORTS = {
    "dispatch_tool": (".utils.route", "dispatch_tool"),
    "reload_skill_index": (".search.skill_search", "reload_skill_index"),
    "reload_mcp_schema": (".callmcp.callmcp", "reload_mcp_schema"),
}


def _load_export(name):
    if name in _SCHEMA_GROUPS:
        return [
            getattr(importlib.import_module(f".{module}", __name__), attr)
            for module, attr in _SCHEMA_GROUPS[name]
        ]
    module_name, attr = _LAZY_EXPORTS[name]
    return getattr(importlib.import_module(module_name, __name__), attr)


def __getattr__(name):
    if name not in _SCHEMA_GROUPS and name not in _LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = _load_export(name)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__))


# --- 系统重型组件初始化逻辑 ---


def init_tools():
    """
    重型类的后台初始化入口。
    利用单个守护线程顺序执行，避免阻塞主进程启动，同时保证初始化的依赖顺序。
    """

    def _bg_init():
        try:
            # 1. 首先确保 MCP 的 Schema 缓存拉取完毕 (否则检索树无法扫描到内容)
            from .callmcp.callmcp import initialize_mcp_sync

            initialize_mcp_sync()

            # 2. 预热本地 Embedding 模型并构建 MCP 检索树
            # 触发单例的 __new__ 初始化，这会在后台加载 ONNX 嵌入模型并执行向量化
            from src.tool.search.mcp_search import MCPSearcher

            print("🚀 正在后台初始化 [MCP] 内存检索树...")
            MCPSearcher()

            # 3. 扫描 skill_dir 结构并构建 Skill 检索树
            from src.tool.search.skill_search import SkillSearcher

            print("🚀 正在后台初始化 [Skill] 内存检索树...")
            SkillSearcher()

            print("✅ 所有重型工具组件后台初始化完毕！")
        except Exception as e:
            import traceback

            print(f"❌ 工具后台初始化异常: {e}")
            traceback.print_exc()

    t = threading.Thread(target=_bg_init, daemon=True, name="InitToolsThread")
    t.start()


# --- 对外严格约束暴露的接口 ---
__all__ = [
    "dispatch_tool",  # 核心路由分发
    "reload_skill_index",  # Skill 重扫描与重新向量化
    "reload_mcp_schema",  # MCP Schema 重建与重载向量化
    "AGENT_TOOL_SCHEMA",  # Agent 默认工具列表
    "BASE_TASK_TOOL_SCHEMA",  # 基础子任务工具列表
    "init_tools",  # 统一的非阻塞初始化入口
]
