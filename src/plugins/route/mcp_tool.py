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
    """MCP 长连接会话管理器 (彻底解决跨 Task 退出报错)"""

    def __init__(self):
        self.sessions = {}
        self.locks = {}
        self.lifecycle_tasks = {}  # 存储各 Server 的专属守护任务
        self.DEFAULT_IDLE_TIMEOUT = 60
        asyncio.run_coroutine_threadsafe(self._idle_cleaner_task(), _mcp_loop)

    async def _get_lock(self, server_name: str) -> asyncio.Lock:
        if server_name not in self.locks:
            self.locks[server_name] = asyncio.Lock()
        return self.locks[server_name]

    async def _server_lifecycle_task(self, server_name: str, config: dict, ready_event: asyncio.Event):
        """专门用于维护单个 MCP Server 生命周期的专属后台任务"""
        server_params = StdioServerParameters(
            command=config["command"],
            args=config.get("args", []),
            env={**os.environ, **config.get("env", {})}
        )
        
        try:
            # 原生的嵌套 async with，完全遵循 SDK 的生命周期管理
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    
                    # 创建一个用于控制退出的内部信号
                    close_event = asyncio.Event()
                    
                    # 存入全局字典
                    self.sessions[server_name] = {
                        "session": session,
                        "last_active": time.time(),
                        "close_event": close_event
                    }
                    
                    # 告诉等待的调用者：连接已就绪！
                    ready_event.set()
                    
                    # 让这个 Task 永久挂起，直到收到关闭信号
                    await close_event.wait()
                    
        except Exception as e:
            # 异常时也要 set，防止调用者无限死锁等待
            ready_event.set()
            print(f"⚠️ [MCP 异常] Server '{server_name}' 运行异常或断开连接: {e}")
        finally:
            # 无论是因为收到信号关闭，还是发生异常崩溃，都在退出前清理字典
            if server_name in self.sessions:
                del self.sessions[server_name]
            if server_name in self.lifecycle_tasks:
                del self.lifecycle_tasks[server_name]

    async def _idle_cleaner_task(self):
        """后台定时清理闲置 Session"""
        while True:
            try:
                await asyncio.sleep(5)  # 每 5 秒检查一次
                now = time.time()
                servers = load_configs()
                
                for server_name in list(self.sessions.keys()):
                    ctx = self.sessions.get(server_name)
                    if not ctx:
                        continue
                    
                    config = servers.get(server_name, {})
                    timeout = config.get("idle_timeout", self.DEFAULT_IDLE_TIMEOUT)
                    
                    if now - ctx["last_active"] > timeout:
                        print(f"🧹 [MCP 资源回收] '{server_name}' 闲置超过 {timeout}s，自动关闭释放资源。")
                        await self._close_session(server_name)
            except Exception as e:
                print(f"⚠️ [MCP 清理器异常] {e}，将继续运行...")
                await asyncio.sleep(1)  # 快速重试

    async def _close_session(self, server_name: str):
        """安全关闭指定的 Session"""
        if server_name in self.sessions:
            # 核心修复：不跨任务调 aclose，而是发信号让它在自己的 Task 里优雅退出
            self.sessions[server_name]["close_event"].set()

    async def shutdown_all(self):
        """关闭所有连接 (优雅退出)"""
        print("\n🛑 [MCP] 正在执行优雅退出，发送关闭信号给所有驻留的子进程...")
        tasks = [self._close_session(name) for name in list(self.sessions.keys())]
        if tasks:
            await asyncio.gather(*tasks)
            # 稍微等一小会儿，给底层断开管道和 kill 进程的时间
            await asyncio.sleep(0.5)
        print("✅ [MCP] 所有子进程已安全清理完毕。")

    async def get_session(self, server_name: str, config: dict) -> ClientSession:
        """获取长连接 Session"""
        lock = await self._get_lock(server_name)

        async with lock:
            if server_name in self.sessions:
                # 刷新最后活跃时间
                self.sessions[server_name]["last_active"] = time.time()
                return self.sessions[server_name]["session"]
            
            print(f"🚀 [MCP] 正在启动 {server_name} 并建立长连接...")
            ready_event = asyncio.Event()
            
            # 启动这个 Server 的专属守护任务
            task = asyncio.create_task(self._server_lifecycle_task(server_name, config, ready_event))
            self.lifecycle_tasks[server_name] = task
            
            # 阻塞等待，直到后台任务把 session 建立完毕并 set() 信号
            # 加入 10 秒超时保护，防止启动失败导致无限等待
            try:
                await asyncio.wait_for(ready_event.wait(), timeout=10.0)
            except asyncio.TimeoutError:
                raise RuntimeError(f"MCP Server '{server_name}' 启动超时 (10s)")
            
            if server_name not in self.sessions:
                raise RuntimeError(f"无法连接到 MCP Server '{server_name}'，进程可能启动即崩溃。")
                
            return self.sessions[server_name]["session"]


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
                    
                    # 1. 解析扩展名
                    ext = mime_type.split('/')[-1] if '/' in mime_type else 'png'
                    if ext == 'jpeg': ext = 'jpg'
                    
                    # 2. 确保存储目录存在
                    save_dir = os.path.join(".buffer", "mcp_media")
                    os.makedirs(save_dir, exist_ok=True)
                    
                    # 3. 将 Base64 解码并保存为实体文件
                    file_path = os.path.join(save_dir, f"mcp_img_{uuid.uuid4().hex[:8]}.{ext}")
                    with open(file_path, "wb") as f:
                        f.write(base64.b64decode(b64_data))
                    
                    # 4. 只将文件路径返回给大模型（彻底告别上下文爆炸）
                    output.append(f"🖼️ [截图/图片已生成并保存至宿主机]: {file_path}")
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