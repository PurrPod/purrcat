"""MCP 会话管理器 - 处理 MCP Server 长连接维护"""

import asyncio
import json
import os
import shutil
import threading
import time
import atexit
from typing import Dict, Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from src.utils.config import get_mcp_config


# 全局事件循环
_mcp_loop = asyncio.new_event_loop()


def _start_mcp_loop():
    """启动 MCP 专用事件循环"""
    asyncio.set_event_loop(_mcp_loop)
    _mcp_loop.run_forever()


# 启动后台线程运行事件循环
_mcp_thread = threading.Thread(target=_start_mcp_loop, name="MCP_EventLoop_Thread", daemon=True)
_mcp_thread.start()


def load_configs() -> dict:
    """加载 MCP Server 配置"""
    try:
        return get_mcp_config().get("mcpServers", {})
    except Exception as e:
        print(f"[MCP 网关] 加载配置文件失败: {e}")
        return {}


class MCPSessionManager:
    """MCP 长连接会话管理器 (解决跨 Task 退出报错问题)"""

    def __init__(self):
        self.sessions: Dict[str, dict] = {}
        self.locks: Dict[str, asyncio.Lock] = {}
        self.lifecycle_tasks: Dict[str, asyncio.Task] = {}  # 存储各 Server 的专属守护任务
        self.DEFAULT_IDLE_TIMEOUT = 3000
        asyncio.run_coroutine_threadsafe(self._idle_cleaner_task(), _mcp_loop)

    async def _get_lock(self, server_name: str) -> asyncio.Lock:
        """获取指定服务器的锁"""
        if server_name not in self.locks:
            self.locks[server_name] = asyncio.Lock()
        return self.locks[server_name]

    async def _server_lifecycle_task(self, server_name: str, config: dict, ready_event: asyncio.Event):
        """维护单个 MCP Server 生命周期的后台任务"""
        raw_command = config["command"]
        resolved_command = shutil.which(raw_command) or raw_command

        server_params = StdioServerParameters(
            command=resolved_command,
            args=config.get("args", []),
            env={**os.environ, **config.get("env", {})}
        )
        
        try:
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    
                    close_event = asyncio.Event()
                    
                    self.sessions[server_name] = {
                        "session": session,
                        "last_active": time.time(),
                        "close_event": close_event
                    }
                    ready_event.set()
                    print(f"✅ 连接到 {server_name} MCP服务器")
                    await close_event.wait()
                    
        except Exception as e:
            ready_event.set()
            print(f"⚠️ [MCP 异常] Server '{server_name}' 运行异常或断开连接: {e}")
        finally:
            if server_name in self.sessions:
                del self.sessions[server_name]
            if server_name in self.lifecycle_tasks:
                del self.lifecycle_tasks[server_name]

    async def _idle_cleaner_task(self):
        """后台定时清理闲置 Session"""
        while True:
            try:
                await asyncio.sleep(5)
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
                await asyncio.sleep(1)

    async def _close_session(self, server_name: str):
        """安全关闭指定的 Session"""
        if server_name in self.sessions:
            self.sessions[server_name]["close_event"].set()

    async def shutdown_all(self):
        """关闭所有连接 (优雅退出)"""
        print("\n🛑 [MCP] 正在执行优雅退出，发送关闭信号给所有驻留的子进程...")
        tasks = [self._close_session(name) for name in list(self.sessions.keys())]
        if tasks:
            await asyncio.gather(*tasks)
            await asyncio.sleep(0.5)
        print("✅ [MCP] 所有子进程已安全清理完毕。")

    async def get_session(self, server_name: str, config: dict) -> ClientSession:
        """获取长连接 Session"""
        lock = await self._get_lock(server_name)

        async with lock:
            if server_name in self.sessions:
                self.sessions[server_name]["last_active"] = time.time()
                return self.sessions[server_name]["session"]
            
            print(f"🚀 [MCP] 正在启动 {server_name} 并建立长连接...")
            ready_event = asyncio.Event()
            
            task = asyncio.create_task(self._server_lifecycle_task(server_name, config, ready_event))
            self.lifecycle_tasks[server_name] = task
            
            try:
                await asyncio.wait_for(ready_event.wait(), timeout=120.0)
            except asyncio.TimeoutError:
                raise RuntimeError(f"MCP Server '{server_name}' 启动超时 (120s)")
            
            if server_name not in self.sessions:
                raise RuntimeError(f"无法连接到 MCP Server '{server_name}'，进程可能启动即崩溃。")
                
            return self.sessions[server_name]["session"]


# 创建单例
mcp_manager = MCPSessionManager()


def _on_system_exit():
    """系统退出时清理资源"""
    future = asyncio.run_coroutine_threadsafe(mcp_manager.shutdown_all(), _mcp_loop)
    try:
        future.result(timeout=5)
    except Exception:
        pass


atexit.register(_on_system_exit)


def _run_sync(coro_func, *args, **kwargs):
    """同步运行异步函数"""
    future = asyncio.run_coroutine_threadsafe(coro_func(*args, **kwargs), _mcp_loop)
    return future.result()