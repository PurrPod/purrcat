import os
import json
import asyncio
import threading
from contextlib import AsyncExitStack
try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
except ImportError:
    raise ImportError("请先安装必需的库: pip install mcp")

CONFIG_PATH = "data\\config\\mcp_config.json"

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

async def _get_mcp_menu_async() -> str:
    servers = load_configs()
    if not servers:
        return "当前未配置任何 MCP Server。请在 mcp/mcp_servers.json 中添加配置。"
    result = "【MCP 外部服务简易菜单】\n"
    result += "💡 提示：如需调用特定工具，请务必先使用 mcp__get_tool_details 获取其详细的参数 Schema。\n"
    for server_name, config in servers.items():
        result += f"\n👉 Server: {server_name}\n"
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
                if not tools_response.tools:
                    result += "   - (该服务当前未提供任何工具)\n"
                for tool in tools_response.tools:
                    desc = tool.description or "无描述"
                    result += f"   - 🔧 工具名: {tool.name} | 描述: {desc}\n"
        except Exception as e:
            result += f"   ❌ [连接失败或获取工具异常]: {str(e)}\n"
    return result

async def _get_tool_details_async(server_name: str, tool_name: str) -> str:
    servers = load_configs()
    if server_name not in servers:
        return f"❌ 未知的 MCP Server '{server_name}'"
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
            tools_response = await session.list_tools()
            for tool in tools_response.tools:
                if tool.name == tool_name:
                    schema_str = json.dumps(tool.inputSchema, ensure_ascii=False, indent=2)
                    return (f"【工具详细说明书】\n"
                            f"Server: {server_name}\n"
                            f"工具名: {tool.name}\n"
                            f"描述: {tool.description or '无描述'}\n"
                            f"参数 Schema:\n{schema_str}\n\n"
                            f"⚠️ 接下来，请严格按照上述 Schema 构造合法的 JSON 字符串，传递给 mcp__call_mcp_tool。")
            return f"❌ 在 Server '{server_name}' 中未找到工具 '{tool_name}'"
    except Exception as e:
        return f"❌ 获取工具详情时发生异常: {str(e)}"

async def _call_tool_async(server_name: str, tool_name: str, arguments: dict) -> str:
    servers = load_configs()
    if server_name not in servers:
        return f"执行失败：未知的 MCP Server '{server_name}'"
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
                return f"❌ 工具内部执行错误: {result.content}"
            output = []
            for content in result.content:
                if content.type == "text":
                    output.append(content.text)
                else:
                    output.append(f"[{content.type} 类型的二进制内容暂不支持直接显示]")
            return "\n".join(output)
    except Exception as e:
        return f"❌ 调用 MCP 进程时发生异常: {str(e)}"

def _run_sync(coro_func, *args, **kwargs):
    result = None
    exception = None
    def worker():
        nonlocal result, exception
        try:
            # asyncio.run 会自动创建新循环、运行协程并安全清理
            result = asyncio.run(coro_func(*args, **kwargs))
        except Exception as e:
            exception = e
    t = threading.Thread(target=worker)
    t.start()
    t.join()  # 阻塞当前环境，直到线程（及内部的异步任务）执行完毕
    if exception:
        raise exception
    return result


# 暴露给外部的纯同步接口
def get_mcp_menu(**kwargs):
    print("[MCP 网关] 正在获取外部服务简易菜单...")
    return _run_sync(_get_mcp_menu_async)


def get_tool_details(server_name: str, tool_name: str, **kwargs):
    print(f"[MCP 网关] 正在获取工具详情: [{server_name}] -> {tool_name}")
    return _run_sync(_get_tool_details_async, server_name, tool_name)


def call_mcp_tool(server_name: str, tool_name: str, arguments: str, **kwargs):
    try:
        args_dict = json.loads(arguments) if arguments else {}
    except json.JSONDecodeError:
        return "执行失败：arguments 必须是合法的 JSON 字符串格式"
    print(f"[MCP 网关] 正在请求 {server_name} 执行 {tool_name} ...")
    return _run_sync(_call_tool_async, server_name, tool_name, args_dict)