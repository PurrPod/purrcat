import base64
import mimetypes
import os
import json
import asyncio
import threading
import uuid
import datetime
import time
import atexit
from contextlib import AsyncExitStack
from typing import Any, List, Dict
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from src.utils.config import get_mcp_servers

_mcp_loop = asyncio.new_event_loop()

def _start_mcp_loop():
    asyncio.set_event_loop(_mcp_loop)
    _mcp_loop.run_forever()


_mcp_thread = threading.Thread(target=_start_mcp_loop, name="MCP_EventLoop_Thread", daemon=True)
_mcp_thread.start()


class MCPSessionManager:
    """MCP 长连接会话管理器"""

    def __init__(self):
        self.sessions = {}
        self.locks = {}
        self.DEFAULT_IDLE_TIMEOUT = 15
        asyncio.run_coroutine_threadsafe(self._idle_cleaner_task(), _mcp_loop)

    async def _get_lock(self, server_name: str) -> asyncio.Lock:
        if server_name not in self.locks:
            self.locks[server_name] = asyncio.Lock()
        return self.locks[server_name]

    async def _idle_cleaner_task(self):
        while True:
            await asyncio.sleep(5)
            now = time.time()
            servers = load_configs()
            
            for server_name in list(self.sessions.keys()):
                ctx = self.sessions.get(server_name)
                if not ctx: continue
                
                config = servers.get(server_name, {})
                timeout = config.get("idle_timeout", self.DEFAULT_IDLE_TIMEOUT)
                
                if now - ctx["last_active"] > timeout:
                    print(f"🧹 [MCP 资源回收] '{server_name}' 闲置超过 {timeout}s，自动关闭释放资源。")
                    await self._close_session(server_name)

    async def _close_session(self, server_name: str):
        ctx = self.sessions.pop(server_name, None)
        if ctx:
            try:
                await ctx["stack"].aclose()
            except Exception as e:
                print(f"⚠️ [MCP] 关闭 Server '{server_name}' 时出现异常: {e}")

    async def shutdown_all(self):
        print("\n🛑 [MCP] 正在执行优雅退出，清理所有驻留的浏览器与子进程...")
        tasks = [self._close_session(name) for name in list(self.sessions.keys())]
        if tasks:
            await asyncio.gather(*tasks)
        print("✅ [MCP] 所有子进程已安全清理完毕。")

    async def get_session(self, server_name: str, config: dict) -> ClientSession:
        lock = await self._get_lock(server_name)

        async with lock:
            if server_name in self.sessions:
                self.sessions[server_name]["last_active"] = time.time()
                return self.sessions[server_name]["session"]

            print(f"🚀 [MCP] 正在启动 {server_name} 并建立长连接...")
            server_params = StdioServerParameters(
                command=config["command"],
                args=config.get("args", []),
                env={**os.environ, **config.get("env", {})}
            )
            stack = AsyncExitStack()
            try:
                read, write = await stack.enter_async_context(stdio_client(server_params))
                session = await stack.enter_async_context(ClientSession(read, write))
                await session.initialize()

                self.sessions[server_name] = {
                    "stack": stack,
                    "session": session,
                    "last_active": time.time()
                }
                return session
            except Exception as e:
                await stack.aclose()
                raise RuntimeError(f"无法连接到 MCP Server {server_name}: {e}")


mcp_manager = MCPSessionManager()

def _on_system_exit():
    future = asyncio.run_coroutine_threadsafe(mcp_manager.shutdown_all(), _mcp_loop)
    try:
        future.result(timeout=5)
    except Exception:
        pass


atexit.register(_on_system_exit)

def _format_response(msg_type: str, content: Any) -> str:
    return json.dumps({"type": msg_type, "content": content}, ensure_ascii=False)


def load_configs() -> dict:
    try:
        return get_mcp_servers()
    except Exception as e:
        print(f"[MCP 网关] 加载配置文件失败: {e}")
        return {}


async def _extract_mcp_fingerprints_async() -> List[Dict]:
    servers = load_configs()
    tools_index = []
    for server_name, config in servers.items():
        try:
            session = await mcp_manager.get_session(server_name, config)
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
    servers = load_configs()
    if server_name not in servers:
        return []
    config = servers[server_name]
    schemas = []
    try:
        session = await mcp_manager.get_session(server_name, config)
        tools_response = await session.list_tools()
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
        raise KeyError(f"未知的 MCP Server '{server_name}'")
    config = servers[server_name]

    try:
        session = await mcp_manager.get_session(server_name, config)
        result = await session.call_tool(tool_name, arguments)

        if server_name in mcp_manager.sessions:
            mcp_manager.sessions[server_name]["last_active"] = time.time()

        if result.isError:
            error_details = "\n".join([c.text for c in result.content if c.type == "text"])
            raise RuntimeError(f"工具业务逻辑执行错误: {error_details}")

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
        return _format_response("text", final_result)

    except RuntimeError as re:
        raise re
    except Exception as e:
        print(f"⚠️ [MCP 异常] 检测到进程奔溃或连接断开: {e}，正在强制清理缓存池...")
        await mcp_manager._close_session(server_name)
        raise RuntimeError(f"MCP 底层连接丢失，请重试以重启服务。详情: {e}")

def _run_sync(coro_func, *args, **kwargs):
    future = asyncio.run_coroutine_threadsafe(coro_func(*args, **kwargs), _mcp_loop)
    return future.result()


def extract_mcp_fingerprints_sync():
    return _run_sync(_extract_mcp_fingerprints_async)


def get_mcp_tool_schemas_sync(server_name: str, tool_names: list):
    return _run_sync(_get_mcp_tool_schemas_async, server_name, tool_names)


def call_mcp_tool(server_name: str, tool_name: str, arguments: dict, **kwargs):
    return _run_sync(_call_tool_async, server_name, tool_name, arguments)