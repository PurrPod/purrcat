"""Coding Expert 扩展工具集

借鉴 Claude Code 工具系统设计，为 CodingTask 提供专业的代码操作能力。

工具列表：
  - file_edit:     search/replace 精确文件编辑（带备份与 diff）
  - code_search:   整合文件查找 + 内容搜索（glob + grep）
  - file_read:     智能文件读取（行范围、行号、上下文）
  - lsp_tool:      代码智能（定义、引用、符号）
  - file_create:   创建新文件（自动建目录，可选覆盖）
"""

import json
from typing import Any

from .file_edit import FILE_EDIT_SCHEMA, execute_file_edit
from .code_search import CODE_SEARCH_SCHEMA, execute_code_search
from .file_read import FILE_READ_SCHEMA, execute_file_read
from .lsp_tool import LSP_SCHEMA, execute_lsp
from .file_create import FILE_CREATE_SCHEMA, execute_file_create

# 所有工具 Schema 列表（CodingTask 通过 get_available_tools 注入）
EXTEND_TOOLS_SCHEMA = [
    FILE_EDIT_SCHEMA,
    CODE_SEARCH_SCHEMA,
    FILE_READ_SCHEMA,
    FILE_CREATE_SCHEMA,
    LSP_SCHEMA,
]

# 工具名 → 实现函数映射
EXTEND_TOOL_FUNCTIONS: dict[str, callable] = {
    "file_edit": execute_file_edit,
    "code_search": execute_code_search,
    "file_read": execute_file_read,
    "file_create": execute_file_create,
    "lsp": execute_lsp,
}


def handle_extend_tool(tool_name: str, arguments: dict, task: Any) -> tuple[bool, str]:
    """统一入口：CodingTask._handle_expert_tool 调用此函数"""
    if tool_name in EXTEND_TOOL_FUNCTIONS:
        return True, EXTEND_TOOL_FUNCTIONS[tool_name](arguments, task)
    return False, ""


def get_extend_tools_schema() -> list[dict]:
    return EXTEND_TOOLS_SCHEMA
