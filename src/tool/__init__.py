from .bash import BASH_TOOL_SCHEMA
from .cron import CRON_TOOL_SCHEMA
from .fetch import FETCH_TOOL_SCHEMA
from .filesystem import FILESYSTEM_TOOL_SCHEMA
from .memo import MEMO_TOOL_SCHEMA
from .search import SEARCH_TOOL_SCHEMA
from .task import TASK_TOOL_SCHEMA
from .callmcp import MCP_TOOL_SCHEMA

AGENT_TOOL_SCHEMA = [BASH_TOOL_SCHEMA,
                     CRON_TOOL_SCHEMA,
                     FETCH_TOOL_SCHEMA,
                     FILESYSTEM_TOOL_SCHEMA,
                     MEMO_TOOL_SCHEMA,
                     SEARCH_TOOL_SCHEMA,
                     TASK_TOOL_SCHEMA,
                     MCP_TOOL_SCHEMA]

__all__ = [AGENT_TOOL_SCHEMA]