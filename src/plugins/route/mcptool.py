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


CONFIG_PATH = "data\\config\\mcp_config.json"


def _format_response(msg_type: str, content: Any) -> str:
    return json.dumps({"type": msg_type, "content": content}, ensure_ascii=False)


def load_configs() -> dict:
    if not os.path.exists(CONFIG_PATH):
        return {}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("mcpServers", {})
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
    servers = load_configs()
    if server_name not in servers:
        return _format_response("error", f"执行失败：未知的 MCP Server '{server_name}'")
    config = servers[server_name]
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
            result = await session.call_tool(tool_name, arguments)
            if result.isError:
                return _format_response("error", f"❌ 工具内部执行错误: {result.content}")
            output = []
            for content in result.content:
                if content.type == "text":
                    output.append(content.text)
                elif content.type == "image" or hasattr(content, "data"):
                    try:
                        mime_type = getattr(content, "mimeType", "image/png")
                        ext = mimetypes.guess_extension(mime_type) or ".bin"
                        base_dir = os.path.dirname(os.path.dirname(
                            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
                        buffer_dir = os.path.join(base_dir, "data", "buffer")
                        os.makedirs(buffer_dir, exist_ok=True)
                        marker_id = uuid.uuid4().hex[:8]
                        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
                        filename = f"mcp_media_{timestamp}_{marker_id}{ext}"
                        filepath = os.path.join(buffer_dir, filename)
                        b64_data = content.data
                        if "," in b64_data and b64_data.startswith("data:"):
                            b64_data = b64_data.split(",", 1)[1]
                        binary_data = base64.b64decode(b64_data)
                        with open(filepath, "wb") as f:
                            f.write(binary_data)
                        output.append(f"🖼️ [检测到 {content.type} 内容，已解码并保存至本地: {filepath} ]")
                    except Exception as e:
                        output.append(f"❌ [{content.type} 类型解析/保存失败: {str(e)}]")
                else:
                    output.append(f"[{content.type} 类型内容]: {str(getattr(content, '__dict__', content))}")

            final_result = "\n".join(output)
            if len(final_result) > 5000:
                base_dir = os.path.dirname(
                    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
                buffer_dir = os.path.join(base_dir, "data", "buffer")
                os.makedirs(buffer_dir, exist_ok=True)
                marker_id = uuid.uuid4().hex[:8]
                timestamp = datetime.datetime.now().strftime("%Y%m%d")
                buffer_path = os.path.join(buffer_dir, f"mcp_result_{timestamp}_{marker_id}.txt")
                with open(buffer_path, "w", encoding="utf-8") as f:
                    f.write(final_result)
                return _format_response(
                    "warning",
                    f"⚠️ [注意] 返回结果过长，已保存至：\n📂 {buffer_path}\n请读取文件获取。"
                )
            return _format_response("text", final_result)
    except Exception as e:
        return _format_response("error", f"❌ 调用 MCP 进程时发生异常: {str(e)}")


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