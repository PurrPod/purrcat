"""
工具总入口，对外暴露路由、Schema、热更新接口和异步初始化方法
"""

import threading

# 导入所有工具的 Schema
from .bash import BASH_TOOL_SCHEMA
from .brainstorm import BRAINSTORM_TOOL_SCHEMA
from .callmcp import MCP_TOOL_SCHEMA
from .cron import CRON_TOOL_SCHEMA
from .fetch import FETCH_TOOL_SCHEMA
from .filesystem import FILESYSTEM_TOOL_SCHEMA
from .memo import MEMO_TOOL_SCHEMA
from .request import REQUEST_TOOL_SCHEMA
from .search import SEARCH_TOOL_SCHEMA
from .task import TASK_TOOL_SCHEMA

# 导入路由模块
from .utils.route import dispatch_tool

# 导入所需的热更新接口
from .search.skill_search import reload_skill_index
from .callmcp.callmcp import reload_mcp_schema, initialize_mcp_sync

# --- 暴露的两套 Schema 列表 ---

AGENT_TOOL_SCHEMA = [
    BASH_TOOL_SCHEMA,
    BRAINSTORM_TOOL_SCHEMA,
    CRON_TOOL_SCHEMA,
    FETCH_TOOL_SCHEMA,
    FILESYSTEM_TOOL_SCHEMA,
    MEMO_TOOL_SCHEMA,
    REQUEST_TOOL_SCHEMA,
    SEARCH_TOOL_SCHEMA,
    TASK_TOOL_SCHEMA,
    MCP_TOOL_SCHEMA,
]

BASE_TASK_TOOL_SCHEMA = [
    BASH_TOOL_SCHEMA,
    FILESYSTEM_TOOL_SCHEMA,
    SEARCH_TOOL_SCHEMA,
    MCP_TOOL_SCHEMA,
    REQUEST_TOOL_SCHEMA,
]

# --- 系统重型组件初始化逻辑 ---


def init_tools():
    """
    重型类的后台初始化入口。
    利用单个守护线程顺序执行，避免阻塞主进程启动，同时保证初始化的依赖顺序。
    """

    def _bg_init():
        try:
            # 1. 首先确保 MCP 的 Schema 缓存拉取完毕 (否则检索树无法扫描到内容)
            initialize_mcp_sync()

            # 2. 预热本地 Embedding 模型并构建 MCP 检索树
            # 触发单例的 __new__ 初始化，这会在后台加载 SentenceTransformer 模型并执行向量化
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
