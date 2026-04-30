"""MCP Schema 管理，负责拉取并缓存 MCP 服务器的 Schema"""

import json
import os
from typing import List, Dict

from src.tool.callmcp.session_manager import mcp_manager, load_configs, _run_sync
from src.utils.config import MCP_SCHEMA_CACHE_FILE


async def _fetch_server_schemas_async(server_name: str, config: dict) -> List[Dict]:
    """异步拉取单个 Server 的 Schema"""
    schemas = []
    try:
        session = await mcp_manager.get_session(server_name, config)
        tools_response = await session.list_tools()
        for tool in tools_response.tools:
            schemas.append({
                "server": server_name,
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": tool.inputSchema
                }
            })
    except Exception as e:
        print(f"警告: [MCP] 拉取 {server_name} Schema 失败: {e}")
    return schemas


async def _fetch_all_schemas_async() -> List[Dict]:
    """异步拉取所有 MCP Server 的 Schema"""
    servers = load_configs()
    all_schemas = []
    for server_name, config in servers.items():
        schemas = await _fetch_server_schemas_async(server_name, config)
        all_schemas.extend(schemas)
    return all_schemas


def fetch_and_cache_schemas() -> List[Dict]:
    """拉取所有 Schema 并写入 JSON 文件"""

    schemas = _run_sync(_fetch_all_schemas_async)

    # 将原本的 jsonl 逐行写入，改为直接作为一个完整的 JSON 数组写入
    with open(MCP_SCHEMA_CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(schemas, f, ensure_ascii=False, indent=4)

    print(f"信息: [MCP] Schema 已缓存至 {MCP_SCHEMA_CACHE_FILE}")
    return schemas


def load_cached_schemas() -> List[Dict]:
    """加载缓存的 Schema"""
    if not os.path.exists(MCP_SCHEMA_CACHE_FILE):
        return fetch_and_cache_schemas()

    try:
        # 从原本的逐行读取 jsonl，改为直接读取整个 JSON 文件
        with open(MCP_SCHEMA_CACHE_FILE, 'r', encoding='utf-8') as f:
            schemas = json.load(f)
            if not isinstance(schemas, list):
                schemas = []
    except Exception as e:
        print(f"警告: [MCP] 读取 Schema 缓存失败: {e}")
        return fetch_and_cache_schemas()

    return schemas


def get_server_schemas(server_name: str) -> List[Dict]:
    """获取指定 Server 的 Schema"""
    schemas = load_cached_schemas()
    return [s for s in schemas if s.get("server") == server_name]


def get_tool_schema(server_name: str, tool_name: str) -> Dict:
    """获取指定工具的 Schema"""
    schemas = load_cached_schemas()
    for s in schemas:
        if s.get("server") == server_name and s.get("function", {}).get("name") == tool_name:
            return s
    return None


def refresh_schemas() -> List[Dict]:
    """强制刷新 Schema 缓存"""
    return fetch_and_cache_schemas()