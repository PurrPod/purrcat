"""MCP Schema 管理器 - 获取并固化 MCP 工具的 Schema"""

import json
import os
from typing import List, Dict

from src.tool.mcp.session_manager import mcp_manager, load_configs, _run_sync


SCHEMA_CACHE_FILE = os.path.join("data", "mcp_schema.jsonl")


def _ensure_cache_dir():
    """确保缓存目录存在"""
    os.makedirs(os.path.dirname(SCHEMA_CACHE_FILE), exist_ok=True)


async def _fetch_server_schemas_async(server_name: str, config: dict) -> List[Dict]:
    """获取单个 Server 的所有工具 Schema"""
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
                    "description": tool.description or "无描述",
                    "parameters": tool.inputSchema
                }
            })
    except Exception as e:
        print(f"❌ [MCP] 获取 {server_name} Schema 失败: {e}")
    return schemas


async def _fetch_all_schemas_async() -> List[Dict]:
    """获取所有 MCP Server 的工具 Schema"""
    servers = load_configs()
    all_schemas = []
    for server_name, config in servers.items():
        schemas = await _fetch_server_schemas_async(server_name, config)
        all_schemas.extend(schemas)
    return all_schemas


def fetch_and_cache_schemas() -> List[Dict]:
    """获取所有 Schema 并缓存到文件"""
    _ensure_cache_dir()
    
    schemas = _run_sync(_fetch_all_schemas_async)
    
    with open(SCHEMA_CACHE_FILE, 'w', encoding='utf-8') as f:
        for schema in schemas:
            f.write(json.dumps(schema, ensure_ascii=False) + '\n')
    
    print(f"✅ [MCP] Schema 已缓存到 {SCHEMA_CACHE_FILE}")
    return schemas


def load_cached_schemas() -> List[Dict]:
    """从缓存文件加载 Schema"""
    if not os.path.exists(SCHEMA_CACHE_FILE):
        return fetch_and_cache_schemas()
    
    schemas = []
    try:
        with open(SCHEMA_CACHE_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    schemas.append(json.loads(line))
    except Exception as e:
        print(f"⚠️ [MCP] 加载缓存 Schema 失败: {e}")
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