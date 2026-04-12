import base64
import mimetypes
import os
import json
import asyncio
import threading
import uuid
import datetime
from contextlib import AsyncExitStack
from typing import Any, List, Dict
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from src.utils.config import get_mcp_servers


def _format_response(msg_type: str, content: Any) -> str:
    return json.dumps({"type": msg_type, "content": content}, ensure_ascii=False)


def load_configs() -> dict:
    try:
        return get_mcp_servers()
    except Exception as e:
        print(f"[MCP 网关] 加载配置文件失败: {e}")
        return {}


async def _extract_mcp_fingerprints_async() -> List[Dict]:
    """为生成统一 tool.jsonl 提供所有 MCP 工具的指纹"""
    servers = load_configs()
    tools_index = []
    for server_name, config in servers.items():
        try:
            server_params = StdioServerParameters(
                command=config["command"],
                args=config.get("args", []),
                env={**os.environ, **config.get("env", {})}
            )
            async with AsyncExitStack() as stack:
                read, write = await stack.enter_async_context(stdio_client(server_params))
                session = await stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                tools_response = await session.list_tools()
                for tool in tools_response.tools:
                    tools_index.append({
                        "route": "mcp",
                        "plugin": server_name,
                        "func": tool.name,
                        "desc": tool.description or "无描述"
                    })
        except Exception as e:
            print(f"❌ [MCP] 获取 {server_name} 工具指纹失败: {e}")
    return tools_index


async def _get_mcp_tool_schemas_async(server_name: str, tool_names: list) -> list:
    """批量获取 dict 格式的 Schema 列表供 fetch_tool 使用，保证只建立一次连接"""
    servers = load_configs()
    if server_name not in servers:
        return []
    config = servers[server_name]
    schemas = []
    try:
        server_params = StdioServerParameters(
            command=config["command"],
            args=config.get("args", []),
            env={**os.environ, **config.get("env", {})}
        )
        async with AsyncExitStack() as stack:
            read, write = await stack.enter_async_context(stdio_client(server_params))
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            tools_response = await session.list_tools()

            # 一次请求拉取所有工具，然后在内存里做批量匹配
            for tool in tools_response.tools:
                if tool.name in tool_names:
                    schemas.append({
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description or "无描述",
                            "parameters": tool.inputSchema
                        }
                    })
    except Exception as e:
        print(f"❌ [MCP] 批量拉取 {server_name} 的 Schema 失败: {e}")
    return schemas





async def _call_tool_async(server_name: str, tool_name: str, arguments: dict) -> str:
    """
    异步调用 MCP 工具（无异常拦截，直接抛给上层）
    """
    servers = load_configs()
    if server_name not in servers:
        raise KeyError(f"未知的 MCP Server '{server_name}'")
    config = servers[server_name]
    
    server_params = StdioServerParameters(
        command=config["command"],
        args=config.get("args", []),
        env={**os.environ, **config.get("env", {})}
    )
    async with AsyncExitStack() as stack:
        read, write = await stack.enter_async_context(stdio_client(server_params))
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        result = await session.call_tool(tool_name, arguments)
        if result.isError:
            raise RuntimeError(f"工具内部执行错误: {result.content}")
        output = []
        for content in result.content:
            if content.type == "text":
                output.append(content.text)
            elif content.type == "image" or hasattr(content, "data"):
                try:
                    mime_type = getattr(content, "mimeType", "image/png")
                    b64_data = content.data
                    if "," in b64_data and b64_data.startswith("data:"):
                        b64_data = b64_data.split(",", 1)[1]
                    output.append({"type": "mcp_media", "mimeType": mime_type, "data": b64_data})
                except Exception as e:
                    output.append(f"❌ [{content.type} 类型解析失败: {str(e)}]")
            else:
                output.append(f"[{content.type} 类型内容]: {str(getattr(content, '__dict__', content))}")

        final_result = output  # 直接返回列表，不再 join
        # ✅ 删除字数限制逻辑，直接返回完整输出
        return _format_response("text", final_result)


def _run_sync(coro_func, *args, **kwargs):
    result = None
    exception = None
    def worker():
        nonlocal result, exception
        try:
            result = asyncio.run(coro_func(*args, **kwargs))
        except Exception as e:
            exception = e
    t = threading.Thread(target=worker)
    t.start()
    t.join()
    if exception:
        raise exception
    return result

def extract_mcp_fingerprints_sync():
    return _run_sync(_extract_mcp_fingerprints_async)

def get_mcp_tool_schemas_sync(server_name: str, tool_names: list):
    """同步调用批量获取"""
    return _run_sync(_get_mcp_tool_schemas_async, server_name, tool_names)

def call_mcp_tool(server_name: str, tool_name: str, arguments: dict, **kwargs):
    return _run_sync(_call_tool_async, server_name, tool_name, arguments)