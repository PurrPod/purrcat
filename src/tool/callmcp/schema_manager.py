"""MCP Schema 管理，负责拉取并缓存 MCP 服务器的 Schema"""

import asyncio
import json
import os
import threading
from typing import Dict, List

from src.tool.callmcp.session_manager import _run_sync, load_configs, mcp_manager
from src.utils.config import MCP_SCHEMA_CACHE_FILE

# 【修复】全局锁，保护 Schema 文件的并发读写
SCHEMA_LOCK = threading.Lock()


async def _fetch_server_schemas_async(server_name: str, config: dict) -> List[Dict]:
    """异步拉取单个 Server 的 Schema"""
    schemas = []
    try:
        session = await mcp_manager.get_session(server_name, config)
        tools_response = await session.list_tools()
        for tool in tools_response.tools:
            schemas.append(
                {
                    "server": server_name,
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description or "",
                        "parameters": tool.inputSchema,
                    },
                }
            )
    except Exception as e:
        print(f"警告: [MCP] 拉取 {server_name} Schema 失败: {e}")
    return schemas


async def _fetch_all_schemas_async() -> List[Dict]:
    """异步并发拉取所有 MCP Server 的 Schema（单服务器慢不再拖垮整体刷新）"""
    servers = load_configs()
    if not servers:
        return []

    results = await asyncio.gather(
        *[
            _fetch_server_schemas_async(server_name, config)
            for server_name, config in servers.items()
        ],
        return_exceptions=True,
    )

    all_schemas = []
    for r in results:
        if isinstance(r, Exception):
            print(f"警告: [MCP] 拉取 Schema 失败: {r}")
        elif r:
            all_schemas.extend(r)
    return all_schemas


def fetch_and_cache_schemas() -> List[Dict]:
    """拉取所有 Schema 并写入 JSONL 文件"""
    with SCHEMA_LOCK:
        schemas = _run_sync(_fetch_all_schemas_async)

        # 确保缓存目录存在
        os.makedirs(os.path.dirname(MCP_SCHEMA_CACHE_FILE), exist_ok=True)

        # 【核心修复】：恢复为 JSONL (逐行 JSON) 格式，修复盲测框架报 index out of bounds 的问题！
        with open(MCP_SCHEMA_CACHE_FILE, "w", encoding="utf-8") as f:
            for schema in schemas:
                f.write(json.dumps(schema, ensure_ascii=False) + "\n")

        print(f"信息: [MCP] Schema 已缓存至 {MCP_SCHEMA_CACHE_FILE}")
        return schemas


def load_cached_schemas() -> List[Dict]:
    """加载缓存的 Schema"""
    with SCHEMA_LOCK:
        if not os.path.exists(MCP_SCHEMA_CACHE_FILE):
            return fetch_and_cache_schemas()

        try:
            schemas = []
            with open(MCP_SCHEMA_CACHE_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    return schemas

                # 【向下兼容】：同时支持读取 JSON 数组和 JSONL，防止残留文件报错
                if content.startswith("["):
                    schemas = json.loads(content)
                else:
                    for line in content.split("\n"):
                        if line.strip():
                            schemas.append(json.loads(line))
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
        if (
            s.get("server") == server_name
            and s.get("function", {}).get("name") == tool_name
        ):
            return s
    return None


def refresh_schemas() -> List[Dict]:
    """强制刷新 Schema 缓存"""
    return fetch_and_cache_schemas()
