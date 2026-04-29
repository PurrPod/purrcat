"""
获取细节。包括 MCP 工具 schema，爬取网页、加载技能、
"""

from .fetch import Fetch
from .schema import FETCH_TOOL_SCHEMA
from .skill_fetch import load_skill
from .web_content_fetch import web_content_fetch
from .mcp_fetch import fetch_mcp_tools

__all__ = ["Fetch", "FETCH_TOOL_SCHEMA", "load_skill", "web_content_fetch", "fetch_mcp_tools"]