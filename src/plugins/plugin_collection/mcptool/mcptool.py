import base64
import mimetypes
import os
import json
import asyncio
import threading
import uuid
import datetime
from contextlib import AsyncExitStack
from typing import Any

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
except ImportError:
    raise ImportError("请先安装必需的库: pip install mcp")

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

async def _get_mcp_menu_async() -> str:
    servers = load_configs()
    if not servers:
        return _format_response("warning", "当前未配置任何 MCP Server。请在 mcp/mcp_servers.json 中添加配置。")
    result = "【MCP 总览菜单】\n"
    result += "💡 提示：如需调用特定工具，请务必先使用 mcptool__get_tool_details 获取其详细的参数 Schema。\n"
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
    return _format_response("text", result)

async def _get_tool_details_async(server_name: str, tool_name: str) -> str:
    servers = load_configs()
    if server_name not in servers:
        return _format_response("error", f"❌ 未知的 MCP Server '{server_name}'")
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
                    content = (f"【工具详细说明书】\n"
                               f"Server: {server_name}\n"
                               f"工具名: {tool.name}\n"
                               f"描述: {tool.description or '无描述'}\n"
                               f"参数 Schema:\n{schema_str}\n\n"
                               f"⚠️ 接下来，请严格按照上述 Schema 构造合法的 JSON 字符串，传递给 mcp__call_mcp_tool。")
                    return _format_response("text", content)
            return _format_response("error", f"❌ 在 Server '{server_name}' 中未找到工具 '{tool_name}'")
    except Exception as e:
        return _format_response("error", f"❌ 获取工具详情时发生异常: {str(e)}")

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
                buffer_filename = f"mcp_result_{timestamp}_{marker_id}.txt"
                buffer_path = os.path.join(buffer_dir, buffer_filename)
                with open(buffer_path, "w", encoding="utf-8") as f:
                    f.write(final_result)
                return _format_response(
                    "warning",
                    f"⚠️ [注意] MCP 工具执行成功，但返回结果过长（共 {len(final_result)} 字符）。\n"
                    f"为防止上下文溢出，完整结果已保存至本地文件：\n"
                    f"📂 {buffer_path}\n"
                    f"👆 请使用 'filesystem__read_file_lines' 或 search 相关工具读取该文件内容。"
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
    t.join()  # 阻塞当前环境，直到线程（及内部的异步任务）执行完毕
    if exception:
        raise exception
    return result
def get_mcp_menu(**kwargs):
    return _run_sync(_get_mcp_menu_async)


def get_tool_details(server_name: str, tool_name: str, **kwargs):
    return _run_sync(_get_tool_details_async, server_name, tool_name)


def call_mcp_tool(server_name: str, tool_name: str, arguments: str, **kwargs):
    try:
        args_dict = json.loads(arguments) if arguments else {}
    except json.JSONDecodeError:
        return _format_response("error", "执行失败：arguments 必须是合法的 JSON 字符串格式")
    return _run_sync(_call_tool_async, server_name, tool_name, args_dict)
